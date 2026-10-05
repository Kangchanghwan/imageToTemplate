#!/bin/bash
# 5라운드: 32B(vlm)를 내리고 A4000 에서 qwen8b / paddle(llama.cpp) / paddle(vLLM) 실측. 어떤 경우에도 종료 시 vlm 복구.
cd ~/sheetparser
LOG=runs/r5/window.log
mkdir -p runs/r5
exec > >(tee -a $LOG) 2>&1
restore() {
  echo "[restore] $(date +%T)"
  docker rm -f q8-test pdl-a4000 pdl-vllm >/dev/null 2>&1
  docker start vlm
  for i in $(seq 1 60); do
    s=$(docker inspect vlm --format '{{.State.Health.Status}}')
    echo "vlm health: $s"; [ "$s" = healthy ] && break; sleep 5
  done
  echo "[restore done] $(date +%T)"
  echo RESTORED > runs/r5/restored.flag
}
trap restore EXIT
rm -f runs/r5/restored.flag
RUN="docker run --rm -u $(id -u):$(id -g) --network host -v $PWD:/w sheetparser python tools/r5.py"
mon() { ( while true; do nvidia-smi --query-gpu=memory.used --format=csv,noheader,nounits -i 0 >> $1; sleep 1; done ) & MONPID=$!; }
echo "[stop vlm] $(date +%T)"; docker stop vlm
# ---- qwen8b ----
docker run -d --name q8-test --gpus all -e CUDA_VISIBLE_DEVICES=0 -v ~/models/qwen3vl:/m -p 127.0.0.1:18002:8080 ghcr.io/ggml-org/llama.cpp:server-cuda -m /m/qwen3vl-8b-q8_0.gguf --mmproj /m/mmproj-8b-f16.gguf -ngl 99 -c 16384 -fa on --jinja --parallel 1 --host 0.0.0.0 --port 8080 -a qwen8b >/dev/null
for i in $(seq 1 60); do curl -sf http://127.0.0.1:18002/health >/dev/null && break; sleep 3; done
echo "[q8 up] $(date +%T)"; rm -f runs/r5/mem_q8.txt; mon runs/r5/mem_q8.txt
$RUN qwen8b runs/r5/q8 all
kill $MONPID; echo "q8 peak MiB: $(sort -n runs/r5/mem_q8.txt | tail -1)"
docker rm -f q8-test >/dev/null; sleep 3
# ---- paddle llama.cpp on A4000 ----
docker run -d --name pdl-a4000 --gpus all -e CUDA_VISIBLE_DEVICES=0 -v ~/models/paddle:/m -p 127.0.0.1:18004:8080 ghcr.io/ggml-org/llama.cpp:server-cuda -m /m/gguf/PaddleOCR-VL-1.6-GGUF.gguf --mmproj /m/gguf/PaddleOCR-VL-1.6-GGUF-mmproj.gguf -ngl 99 -c 8192 --parallel 4 --host 0.0.0.0 --port 8080 --jinja -a paddle >/dev/null
for i in $(seq 1 60); do curl -sf http://127.0.0.1:18004/health >/dev/null && break; sleep 3; done
echo "[paddle a4000 up] $(date +%T)"; rm -f runs/r5/mem_pa.txt; mon runs/r5/mem_pa.txt
PADDLE_URL=http://127.0.0.1:18004/v1/chat/completions PADDLE_PAD=3 PADDLE_WORKERS=4 bash -c "$RUN paddle runs/r5/pa all"
kill $MONPID; echo "paddle a4000 peak MiB: $(sort -n runs/r5/mem_pa.txt | tail -1)"
docker rm -f pdl-a4000 >/dev/null; sleep 3
# ---- paddle vLLM on A4000 (시도) ----
docker run -d --name pdl-vllm --gpus all -e CUDA_VISIBLE_DEVICES=0 -v ~/models/paddle/hf:/hf -p 127.0.0.1:18005:8000 vllm/vllm-openai:v0.29.0-cu129 --model /hf --served-model-name paddle --trust-remote-code --gpu-memory-utilization 0.45 --max-model-len 4096 --max-num-batched-tokens 16384 --no-enable-prefix-caching --mm-processor-cache-gb 0 --max-num-seqs 16 >/dev/null
for i in $(seq 1 60); do curl -sf http://127.0.0.1:18005/health >/dev/null && break; sleep 5; done
if curl -sf http://127.0.0.1:18005/health >/dev/null; then
  echo "[paddle vllm up] $(date +%T)"; rm -f runs/r5/mem_pv.txt; mon runs/r5/mem_pv.txt
  PADDLE_URL=http://127.0.0.1:18005/v1/chat/completions PADDLE_PAD=3 PADDLE_WORKERS=8 bash -c "$RUN paddle runs/r5/pv all"
  kill $MONPID; echo "paddle vllm peak MiB: $(sort -n runs/r5/mem_pv.txt | tail -1)"
else
  echo "[paddle vllm FAILED]"; docker logs pdl-vllm 2>&1 | tail -30
fi
echo ALLDONE
