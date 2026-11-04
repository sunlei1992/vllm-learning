FROM sim030:glm53
RUN apt-get update -qq \
    && apt-get install -y -qq libcurl4 libibverbs1 rdma-core librdmacm1 libnuma1 liburing2 \
    && rm -rf /var/lib/apt/lists/*
RUN /opt/v030/bin/python -m pip install --no-cache-dir mooncake-transfer-engine-non-cuda
