export SCRIPT_PATH=$(dirname "$(readlink -f "$0")")
export LD_LIBRARY_PATH=${LD_LIBRARY_PATH}:/usr/local/Ascend/ascend-toolkit/latest/opp/vendors/CAM/op_api/lib
export LD_LIBRARY_PATH=${LD_LIBRARY_PATH}:${SCRIPT_PATH}/src/build_out/comm_operator/lib
export PYTHONPATH="${PYTHONPATH}:${SCRIPT_PATH}/build/cam/comm_operator"
# export ASCEND_RT_VISIBLE_DEVICES=0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15
export MOE_USE_1C2V=1

cd ${SCRIPT_PATH}/
find . -name "*.sh" | xargs -i chmod +x {}
find . -name "*.sh" | xargs -i dos2unix {}

# bash build/cam/build.sh -c ascend910b4
enable_profiling=$(python -c "import trace_utils, sys; sys.exit(1 if trace_utils.get_enable_moe_profiling() == 0 else 0)" > /dev/null 2>&1 && echo true || echo false)

case $1 in
    0)
        echo "build"
        bash build/cam/build.sh -c ascend910_93 || exit
        bash output/cam/comm_operator/run/CAM_ascend910_93*.run || exit
        pip install --force-reinstall output/cam/comm_operator/dist/umdk_cam_op*.whl || exit
        ;;
    1)
        TEST_TAG="debug"
        echo "run"
        python src/cam/examples/fused_deep_moe_sample.py
        if $enable_profiling; then
            python build/cam/comm_operator/trace_collector.py ${SCRIPT_PATH}/output/cam/profiling_data ${SCRIPT_PATH}/output/cam/point_map.json -o ${SCRIPT_PATH}/output/cam/trace-${TEST_TAG}.json
            python build/cam/comm_operator/trace_collector.py --depth 1 ${SCRIPT_PATH}/output/cam/profiling_data ${SCRIPT_PATH}/output/cam/point_map.json -o ${SCRIPT_PATH}/output/cam/trace-${TEST_TAG}-leaf.json
        fi
        cd ${SCRIPT_PATH}/output/cam/
        rm -fr trace.tar.gz
        tar -czf trace.tar.gz trace-*.json
        echo "trace saved to ${SCRIPT_PATH}/output/cam/"
        cd ${SCRIPT_PATH}/
        ;;
    2)
        python build/cam/comm_operator/trace_save.py $2 --rank 0
        python build/cam/comm_operator/trace_collector.py ${SCRIPT_PATH}/output/cam/profiling_data ${SCRIPT_PATH}/output/cam/point_map.json -o ${SCRIPT_PATH}/output/cam/trace.json
        ;;
    *)
        echo "invalid argument"
        ;;
esac