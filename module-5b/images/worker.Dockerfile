FROM registry.vcloud.example.com/vllm/vllm-openai:v0.31.0
COPY module-5b/runtime/gpu-check.py /opt/vcloud/gpu-check.py
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/tmp HF_HUB_OFFLINE=1
USER 65532:65532
WORKDIR /tmp
ENTRYPOINT ["python", "/opt/vcloud/gpu-check.py"]
