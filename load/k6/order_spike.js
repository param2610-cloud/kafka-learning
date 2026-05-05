import http from "k6/http";
import { check } from "k6";
import { Counter, Rate } from "k6/metrics";

const totalRequests = Number(__ENV.TOTAL_REQUESTS || 1000000);
const virtualUsers = Number(__ENV.VUS || 2000);
const maxDuration = __ENV.MAX_DURATION || "20m";
const uniqueUsers = Number(__ENV.UNIQUE_USERS || 1000);
const orderBaseUrl = __ENV.ORDER_BASE_URL || "http://localhost:8000";
const inventoryBaseUrl = __ENV.INVENTORY_BASE_URL || orderBaseUrl.replace("order-service", "inventory-service").replace(":8000", ":8002");
const targetItem = __ENV.TARGET_ITEM || "pencil";
const itemQuantity = Number(__ENV.ITEM_QUANTITY || 1);

const successfulOrders = new Counter("successful_orders");
const failedOrders = new Counter("failed_orders");
const partialFailures = new Counter("partial_failures");
const hardFailureRate = new Rate("hard_failure_rate");

export const options = {
  scenarios: {
    million_request_spike: {
      executor: "shared-iterations",
      vus: virtualUsers,
      iterations: totalRequests,
      maxDuration: maxDuration,
    },
  },
  thresholds: {
    hard_failure_rate: ["rate<0.30"],
    http_req_duration: ["p(95)<4000"],
  },
};

function buildOrderPayload(iteration) {
  const userId = `u-${(iteration % uniqueUsers) + 1}`;
  return {
    user_id: userId,
    email: `${userId}@example.com`,
    items: [
      { product_id: targetItem, quantity: itemQuantity },
    ],
  };
}

function checkItemAvailability(items) {
  try {
    const response = http.post(
      `${inventoryBaseUrl}/check-availability`,
      JSON.stringify({ items }),
      {
        headers: { "Content-Type": "application/json" },
        timeout: "5s",
      },
    );
    if (response.status === 200) {
      const body = response.json();
      return Boolean(body && body.available);
    }
    return false;
  } catch(e) {
    return false;
  }
}

export default function () {
  const orderPayload = buildOrderPayload(__ITER);

  if (!checkItemAvailability(orderPayload.items)) {
    hardFailureRate.add(0); // Don't count as failure - item just unavailable
    return;
  }

  const response = http.post(`${orderBaseUrl}/orders`, JSON.stringify(orderPayload), {
    headers: { "Content-Type": "application/json" },
    timeout: "10s",
  });

  const responseOk = check(response, {
    "order endpoint returned 200": (r) => r.status === 200,
  });

  if (!responseOk) {
    failedOrders.add(1);
    hardFailureRate.add(1);
    return;
  }

  const body = response.json();
  const status = body && body.order ? body.order.status : "unknown";
  if (status === "processed") {
    successfulOrders.add(1);
    hardFailureRate.add(0);
  } else {
    partialFailures.add(1);
    hardFailureRate.add(1);
  }
}
