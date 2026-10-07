# Vendored Argo CD installation

`argocd-v3.5.3-install.yaml.gz` contains the exact upstream v3.5.3 installation
manifest from the URL in `../registry-images.lock.json`. Argo CD is distributed
under [Apache License 2.0](https://github.com/argoproj/argo-cd/blob/v3.5.3/LICENSE).
The lock verifies compressed and uncompressed bytes. `tools/airgap.py` derives
the local base by normalizing pull policies; it never downloads during rendering.
