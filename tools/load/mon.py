"""호스트(elgrim)에서 실행하는 부하 모니터. 1초 간격으로 CPU%, loadavg, GPU 메모리/사용률, paddle/vlm 슬롯 점유를 기록한다.
사용: python3 mon.py <out.json> (SIGTERM 으로 종료하면 요약 JSON 저장)"""
import json, signal, subprocess, sys, time, urllib.request

out = sys.argv[1]
stop = []
signal.signal(signal.SIGTERM, lambda *a: stop.append(1))
signal.signal(signal.SIGINT, lambda *a: stop.append(1))


def cpu():
    v = [int(x) for x in open("/proc/stat").readline().split()[1:]]
    return sum(v), v[3] + v[4]


def slots(port):
    try:
        s = json.load(urllib.request.urlopen("http://127.0.0.1:%d/slots" % port, timeout=1))
        return sum(1 for x in s if x.get("is_processing"))
    except Exception:
        return -1


rows = []
t0, i0 = cpu()
while not stop:
    t1, i1 = cpu()
    c = 100.0 * (1 - (i1 - i0) / max(1, t1 - t0)); t0, i0 = t1, i1
    g = subprocess.run(["nvidia-smi", "--query-gpu=index,memory.used,utilization.gpu", "--format=csv,noheader,nounits"],
                       stdout=subprocess.PIPE, universal_newlines=True).stdout.strip().splitlines()
    gp = [[int(x) for x in l.split(",")] for l in g]
    rows.append({"t": time.time(), "cpu": c, "load1": float(open("/proc/loadavg").read().split()[0]),
                 "gmem": [x[1] for x in gp], "gutil": [x[2] for x in gp], "paddle_busy": slots(18003), "vlm_busy": slots(18001)})
    time.sleep(1)


def mx(k, i=None):
    v = [r[k] if i is None else r[k][i] for r in rows]
    return max(v) if v else None


def avg(k, i=None):
    v = [r[k] if i is None else r[k][i] for r in rows]
    return sum(v) / len(v) if v else None


s = {"samples": len(rows), "cpu_avg": avg("cpu"), "cpu_max": mx("cpu"), "load1_max": mx("load1"),
     "gmem_max": [mx("gmem", i) for i in range(3)], "gutil_avg": [avg("gutil", i) for i in range(3)], "gutil_max": [mx("gutil", i) for i in range(3)],
     "paddle_busy_avg": avg("paddle_busy"), "paddle_busy_max": mx("paddle_busy"), "vlm_busy_avg": avg("vlm_busy"), "vlm_busy_max": mx("vlm_busy")}
json.dump(s, open(out, "w"))
