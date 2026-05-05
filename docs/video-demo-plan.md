# Kafka Lab LinkedIn Demo Plan

This is a short recording plan, not a tutorial. The goal is to show that KEDA
and Redis were added because the system created visible pain under load.

## Core Message

Do not start with tools. Start with pain.

> I did not add Kafka, KEDA, or Redis because they are popular. I added each one
> only after the system showed a real failure mode under traffic.

## Video Shape

Target length: 3 to 5 minutes.

1. Problem 1: Email confirmation delay.
2. Fix 1: KEDA for email consumers.
3. Problem 2: Stock shown as available while orders are already queued.
4. Fix 2: Redis-backed stock reservation.
5. Closing principle: use infrastructure when the failure mode demands it.

## Spoken Script

### Opening

> I built a small order system with three services: order, email, and inventory.
> The order service does not call email and inventory directly. It publishes an
> order-created event to Kafka, and the email and inventory services consume it.
>
> This looks clean, but under traffic two real problems appear.

### Demo 1: Email Delay Before KEDA

Show:

- Load Orchestrator running a spike.
- Grafana or logs showing many order events produced.
- Email service stuck at a low replica count.
- Kafka lag or delayed email processing increasing.

Say:

> First pain: the order API is still fast because Kafka accepts the events, but
> confirmation emails are delayed. The email service has no awareness that Kafka
> lag is growing. From inside the service, it just processes messages one by one.
>
> So CPU-based scaling is not always the right signal here. The real signal is
> not CPU. The real signal is Kafka lag.

### Demo 1 Fix: KEDA For Email

Show:

- KEDA ScaledObject for email-service.
- Email replicas increasing when lag grows.
- Lag recovering faster.

Say:

> This is where KEDA fits. KEDA watches Kafka lag and tells Kubernetes to add
> email consumers when the queue grows.
>
> I am not using KEDA everywhere. I am using it where the queue delay is the
> actual business pain: confirmation email latency.

### Demo 2: Stock Problem Before Redis Reservation

Show:

- Small stock, for example pencil = 10.
- Load spike larger than stock.
- Many orders get accepted or queued.
- Inventory later rejects or fails to reduce some of them.
- User-visible stock is not reflecting the queued demand quickly enough.

Say:

> Second pain: inventory. Kafka protects the order API from slowing down, but it
> also means inventory is updated later.
>
> During a spike, users can still see stock as available while many orders are
> already queued. The order is accepted first, and the stock reduction happens
> later in the inventory consumer.
>
> That creates a bad user experience: the system appears to accept demand that
> inventory cannot actually fulfill.

### Demo 2 Fix: Redis Reservation

Show:

- Redis stock initialized.
- Atomic reserve happens before order acceptance.
- Once stock reaches zero, new orders are rejected immediately.
- Inventory event no longer double-decrements the same stock.

Say:

> The fix is not simply adding more inventory pods. That could make the database
> hotter and still does not solve the user-facing race.
>
> The fix is to move the stock decision to a fast shared state: Redis. At the
> order boundary, I atomically reserve stock. If Redis says stock is gone, the
> order is rejected immediately.
>
> Kafka still remains useful. It buffers follow-up work. But Redis protects the
> decision that must be correct before accepting the order.

### Closing

> That is the point of this experiment. I did not start with "we need KEDA" or
> "we need Redis." I started with pain:
>
> email delay under Kafka backlog, solved with KEDA;
> stock race under async inventory updates, solved with Redis reservation.
>
> Tools should be introduced because the system proves that it needs them.

## Recording States

### State A: Email Pain, Before KEDA

Expected behavior:

- Kafka enabled.
- Email replicas fixed low.
- KEDA not installed or not applied.
- Email provider delay enabled.
- Under load, Kafka lag grows and email processing falls behind.

Useful commands:

```powershell
kubectl -n kafka-lab scale deployment/email-service --replicas=1
kubectl -n kafka-lab set env deployment/email-service EMAIL_PROVIDER_API_DELAY_SECONDS=0.2
kubectl -n kafka-lab rollout status deployment/email-service --timeout=180s
```

Run load from the Load Orchestrator UI:

- total requests: 2000 to 10000
- VUs: 100 to 300
- item quantity: 1
- target item: pencil

### State B: Email Fix, With KEDA

Expected behavior:

- KEDA CRDs/operator installed.
- Only email-service has a ScaledObject.
- Email replicas increase when Kafka lag grows.

Check KEDA exists:

```powershell
kubectl get crd scaledobjects.keda.sh
kubectl -n kafka-lab get scaledobject
```

Apply email KEDA:

```powershell
kubectl apply -f k8s/keda.yaml
kubectl -n kafka-lab get scaledobject email-service-keda
```

Important: inventory should not be KEDA-scaled for this demo.

### State C: Stock Pain, Before Redis Reservation

Expected behavior:

- Kafka enabled.
- Order service accepts orders quickly.
- Inventory updates happen later from Kafka.
- With low stock and high load, orders can be accepted before inventory catches up.

Suggested setup:

```powershell
kubectl -n kafka-lab exec deployment/inventory-service -- python -c "import urllib.request,json; req=urllib.request.Request('http://localhost:8002/stock', data=json.dumps({'pencil':10,'notebook':50,'eraser':75}).encode(), headers={'Content-Type':'application/json'}, method='POST'); print(urllib.request.urlopen(req).read().decode())"
```

Run more than 10 pencil orders.

### State D: Stock Fix, With Redis Reservation

Expected behavior:

- Redis enabled.
- Order service reserves stock atomically before accepting the order.
- Inventory event does not decrement the same stock again.
- Once Redis stock reaches zero, new orders are rejected immediately.

Current implementation note:

The order service now atomically reserves Redis stock before publishing the
Kafka event. The event carries inventory reservation metadata, and the inventory
consumer treats that event as already reserved instead of decrementing stock a
second time.

This means the demo can honestly show that once Redis stock reaches zero, new
orders are rejected at the order boundary before they are queued to Kafka.

## What To Keep Off Camera

- Do not explain every manifest.
- Do not walk through all code.
- Do not frame this as "KEDA is better than HPA."
- Do not say Redis solves everything.

Keep the language practical:

> HPA scales compute pressure.
> KEDA scales queue pressure.
> Redis protects fast shared state decisions.
> Kafka protects the API from downstream delay.

## One-Line LinkedIn Caption

I used Kafka, KEDA, and Redis only after the system showed why it needed them:
Kafka buffered work, KEDA handled email backlog, and Redis protected stock
decisions before accepting orders.
