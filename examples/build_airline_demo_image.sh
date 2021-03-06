#!/bin/bash

set -eux

ROOT=$(git rev-parse --show-toplevel)
pushd $ROOT/examples

pip install --upgrade pip

function cleanup {
    rm -rf dagster
    rm -rf dagster-graphql
    rm -rf dagstermill
    rm -rf dagster-aws
}
# ensure cleanup happens on error or normal exit
trap cleanup EXIT

cp -R ../python_modules/dagster .
cp -R ../python_modules/dagster-graphql .
cp -R ../python_modules/dagstermill .
cp -R ../python_modules/libraries/dagster-aws .

rm -rf dagster/.tox
rm -rf dagster-graphql/.tox
rm -rf dagstermill/.tox
rm -rf dagster-aws/.tox

rm -rf dagster/dist
rm -rf dagster-graphql/dist
rm -rf dagstermill/dist
rm -rf dagster-aws/dist

rm -rf .tox dist

docker build -t airline-demo-airflow .
docker tag airline-demo-airflow dagster/airline-demo-airflow
