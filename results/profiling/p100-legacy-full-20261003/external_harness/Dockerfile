FROM airsim-rf:p100-sionna-0.19.2-cuda
RUN python -m pip install --no-cache-dir nvtx==0.2.13
COPY --from=airsim-rf:p100-profile /opt/airsim-rf /opt/airsim-rf
ENV PYTHONPATH=/work/harness:/opt/airsim-rf/src MPLCONFIGDIR=/tmp/matplotlib MPLBACKEND=Agg TF_FORCE_GPU_ALLOW_GROWTH=true TF_CPP_MIN_LOG_LEVEL=2 RF_PROFILE_SOURCE_REV=720c4011522ad25c1e9c5c470bc20f4f34d480c5 RF_PROFILE_SOURCE_DIRTY=false
WORKDIR /opt/airsim-rf
ENTRYPOINT ["python"]
