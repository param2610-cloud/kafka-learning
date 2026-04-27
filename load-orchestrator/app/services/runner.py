import os
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from time import sleep
from uuid import uuid4

from kubernetes import client, config
from kubernetes.client import ApiException

from app.models.schemas import RunSummary, StartRunRequest


@dataclass
class RunRecord:
    summary: RunSummary


RUNS: dict[str, RunRecord] = {}


def _load_kube_config() -> None:
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()


def _batch_api() -> client.BatchV1Api:
    _load_kube_config()
    return client.BatchV1Api()


def _core_api() -> client.CoreV1Api:
    _load_kube_config()
    return client.CoreV1Api()


def _apps_api() -> client.AppsV1Api:
    _load_kube_config()
    return client.AppsV1Api()


def _namespace() -> str:
    return os.getenv("TARGET_NAMESPACE", "kafka-lab")


def start_run(request: StartRunRequest) -> RunSummary:
    run_id = str(uuid4())[:8]
    job_name = f"k6-run-{run_id}"
    namespace = _namespace()

    env = [
        client.V1EnvVar(name="TOTAL_REQUESTS", value=str(request.total_requests)),
        client.V1EnvVar(name="VUS", value=str(request.vus)),
        client.V1EnvVar(name="MAX_DURATION", value=request.max_duration),
        client.V1EnvVar(name="UNIQUE_USERS", value=str(request.unique_users)),
        client.V1EnvVar(name="ORDER_BASE_URL", value=request.order_base_url),
    ]

    container = client.V1Container(
        name="k6",
        image="grafana/k6:1.2.3",
        command=["k6", "run", "/scripts/order_spike.js"],
        env=env,
        volume_mounts=[client.V1VolumeMount(name="k6-script", mount_path="/scripts")],
        resources=client.V1ResourceRequirements(
            requests={"cpu": "500m", "memory": "512Mi"},
            limits={"cpu": "2000m", "memory": "2Gi"},
        ),
    )

    template = client.V1PodTemplateSpec(
        metadata=client.V1ObjectMeta(labels={"app": "k6-runner", "run_id": run_id}),
        spec=client.V1PodSpec(
            restart_policy="Never",
            containers=[container],
            volumes=[
                client.V1Volume(
                    name="k6-script",
                    config_map=client.V1ConfigMapVolumeSource(name="k6-script-config"),
                )
            ],
        ),
    )

    spec = client.V1JobSpec(template=template, backoff_limit=0, ttl_seconds_after_finished=900)
    job = client.V1Job(
        api_version="batch/v1",
        kind="Job",
        metadata=client.V1ObjectMeta(name=job_name, namespace=namespace),
        spec=spec,
    )

    _batch_api().create_namespaced_job(namespace=namespace, body=job)

    summary = RunSummary(
        run_id=run_id,
        job_name=job_name,
        namespace=namespace,
        status="running",
        created_at=datetime.now(UTC),
        request=request,
    )
    RUNS[run_id] = RunRecord(summary=summary)

    if request.chaos.enabled:
        thread = threading.Thread(
            target=_chaos_worker,
            args=(request.chaos.target_service, request.chaos.outage_seconds, request.chaos.recovery_replicas),
            daemon=True,
        )
        thread.start()

    return summary


def list_runs() -> list[RunSummary]:
    return [record.summary for record in RUNS.values()]


def stop_run(run_id: str) -> bool:
    record = RUNS.get(run_id)
    if not record:
        return False

    try:
        _batch_api().delete_namespaced_job(
            name=record.summary.job_name,
            namespace=record.summary.namespace,
            propagation_policy="Foreground",
        )
    except ApiException as exc:
        if exc.status != 404:
            raise

    record.summary.status = "stopped"
    return True


def get_run_status(run_id: str) -> dict | None:
    record = RUNS.get(run_id)
    if not record:
        return None

    summary = record.summary
    result = {
        "run": summary,
        "active": True,
        "succeeded": None,
        "failed": None,
        "completion_time": None,
        "last_log_excerpt": None,
    }

    try:
        job = _batch_api().read_namespaced_job(name=summary.job_name, namespace=summary.namespace)
        status = job.status
        result["succeeded"] = status.succeeded
        result["failed"] = status.failed
        if status.completion_time:
            result["completion_time"] = status.completion_time
        if status.active is None or status.active == 0:
            result["active"] = False
            if status.succeeded:
                summary.status = "succeeded"
            elif status.failed:
                summary.status = "failed"
    except ApiException as exc:
        if exc.status == 404:
            result["active"] = False
            summary.status = "not-found"
        else:
            raise

    pods = _core_api().list_namespaced_pod(
        namespace=summary.namespace,
        label_selector=f"job-name={summary.job_name}",
    )
    if pods.items:
        pod_name = pods.items[0].metadata.name
        try:
            logs = _core_api().read_namespaced_pod_log(
                name=pod_name,
                namespace=summary.namespace,
                tail_lines=30,
            )
            result["last_log_excerpt"] = logs
        except ApiException:
            pass

    return result


def _chaos_worker(target_service: str, outage_seconds: int, recovery_replicas: int) -> None:
    apps = _apps_api()
    namespace = _namespace()

    original_replicas = recovery_replicas
    try:
        scale_obj = apps.read_namespaced_deployment_scale(name=target_service, namespace=namespace)
        if scale_obj.spec and scale_obj.spec.replicas is not None:
            original_replicas = scale_obj.spec.replicas
    except ApiException:
        pass

    body_down = {"spec": {"replicas": 0}}
    apps.patch_namespaced_deployment_scale(name=target_service, namespace=namespace, body=body_down)

    sleep(outage_seconds)

    body_up = {"spec": {"replicas": recovery_replicas or original_replicas or 1}}
    apps.patch_namespaced_deployment_scale(name=target_service, namespace=namespace, body=body_up)
