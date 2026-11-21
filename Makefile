.PHONY := clean decrypt encrypt install test lint format package init validate plan apply deploy update-deps

ifndef AWS_SESSION_TOKEN
  $(error Not logged in, please run 'awsume')
endif

clean:
	@rm -rf \
	terraform/.terraform \
	terraform/.terraform.lock.hcl \
	terraform/lambda.zip \
	terraform/secrets.yaml \
	lambda.zip \
	.pytest_cache \
	*/__pycache__ \
	aws_idc_pim/__pycache__ \
	tests/__pycache__

decrypt:
	@aws kms decrypt \
	--ciphertext-blob $$(cat terraform/secrets.yaml.encrypted) \
	--output text \
	--query Plaintext \
	--encryption-context target=aws-idc-pim | base64 -d > terraform/secrets.yaml

encrypt:
	@aws kms encrypt \
	--key-id alias/generic \
	--plaintext fileb://terraform/secrets.yaml \
	--encryption-context target=aws-idc-pim \
	--output text \
	--query CiphertextBlob > terraform/secrets.yaml.encrypted
	@rm -f terraform/secrets.yaml

install:
	@uv sync --all-extras

test: install
	@uv run pytest

lint:
	@uv run pylint aws_idc_pim tests

package:
	@rm -f lambda.zip
	@zip -r lambda.zip aws_idc_pim -x "aws_idc_pim/__pycache__/*"
	@uv pip install --target build_deps pynacl urllib3 >/dev/null
	@cd build_deps && zip -r ../lambda.zip . -x "*.dist-info/*"
	@rm -rf build_deps

init:
	@terraform -chdir=terraform init

validate: init
	@terraform -chdir=terraform validate

apply: validate decrypt
	@terraform -chdir=terraform apply -input=true -refresh=true

deploy: package
	@aws lambda update-function-code --function-name aws-idc-pim --zip-file fileb://lambda.zip

format: install
	@uv run ruff format .
	@uv run ruff check --fix .

update-deps:
	@uv sync --upgrade --all-extras

plan: init decrypt
	@terraform -chdir=terraform plan
