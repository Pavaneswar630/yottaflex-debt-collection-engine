#!/bin/sh
set -eu

loans="${YOTTAFLEX_LOANS:-10000}"
dataset_dir="${YOTTAFLEX_DATA_DIR:-/app/data/full}"
truth_dir="${YOTTAFLEX_GROUND_TRUTH_DIR:-/app/ground_truth/full}"
database="${YOTTAFLEX_DB_PATH:-${dataset_dir}/collection.sqlite}"

if [ ! -f "${dataset_dir}/manifest.json" ]; then
    python -m yottaflex_debt_collection \
        --dataset full \
        --loans "${loans}" \
        --seed "${YOTTAFLEX_SEED:-20261022}" \
        --output-dir /app
fi

if [ ! -f "${database}" ]; then
    python -m yottaflex_debt_collection.database \
        --data-dir "${dataset_dir}" \
        --ground-truth-dir "${truth_dir}" \
        --db "${database}"
fi

exec python -m yottaflex_debt_collection.api
