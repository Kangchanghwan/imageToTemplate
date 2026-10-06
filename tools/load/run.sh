#!/bin/sh
# elgrim 에서 실행: tools/load/run.sh <tag> <load.py args...>  (모니터 + 컨테이너 1개, 전후로 RestartCount/OOM 기록)
cd ~/sheetparser; mkdir -p runs/load
TAG=$1; shift
python3 tools/load/mon.py runs/load/$TAG.mon.json & MP=$!
sleep 2
S=$(date +%s.%N)
docker run --rm -u $(id -u):$(id -g) --network host -v $PWD:/w -w /w -e PYTHONPATH=/w sheetparser python tools/load/load.py "$@" --tag $TAG
kill $MP; wait $MP
echo "mon: $(cat runs/load/$TAG.mon.json)"
echo "health: $(docker inspect -f '{{.Name}} rc={{.RestartCount}} oom={{.State.OOMKilled}}' vlm paddle | tr '\n' ' ')"
