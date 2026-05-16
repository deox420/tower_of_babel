PY  ?= python
PIP ?= pip

.PHONY: install run-server run-server-insecure run-client-clearnet run-client-onion \
        build build-docker certs clean lock verify-checksums

install:
	$(PIP) install -r requirements.txt

certs:
	$(PY) -c "from server.main import generate_selfsigned; generate_selfsigned('cert.pem','key.pem')"

run-server:
	$(PY) -m server --cert cert.pem --key key.pem --host 127.0.0.1

run-server-insecure:
	$(PY) -m server --insecure --host 127.0.0.1

run-client-clearnet:
	$(PY) -m client --clearnet --insecure --server ws://127.0.0.1:8765

run-client-onion:
	@if [ -z "$(ONION)" ]; then echo "ONION=<addr.onion[:8765]> required"; exit 1; fi
	$(PY) -m client --onion $(ONION)

# Reproducible build on the current host. Two consecutive runs produce
# byte-identical binaries thanks to pinned SOURCE_DATE_EPOCH and
# PYTHONHASHSEED.
build:
	bash packaging/build.sh

# Reproducible build inside the pinned Docker image (official release path).
build-docker:
	docker build -f packaging/Dockerfile.build -t void-build:$$(cat VERSION) .
	docker run --rm -v "$$PWD/dist:/src/dist" void-build:$$(cat VERSION)

# Regenerate the hash-pinned requirements lock. Requires pip-tools.
lock:
	$(PIP) install --upgrade pip-tools
	pip-compile --generate-hashes --output-file requirements.lock requirements.txt

verify-checksums:
	cd dist && sha256sum -c SHA256SUMS

clean:
	rm -rf build dist *.spec.bak __pycache__ */__pycache__ */*/__pycache__ \
	       cert.pem key.pem
