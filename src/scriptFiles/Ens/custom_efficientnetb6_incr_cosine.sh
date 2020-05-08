#!/usr/bin/env bash
#SBATCH --mem  12GB
#SBATCH --gres gpu:4
#SBATCH --cpus-per-task 2
#SBATCH --mail-type FAIL
#SBATCH --mail-user ferles@kth.se
#SBATCH --output /Midgard/home/%u/Dermatology/logs/custom_eb6_incr_cosine.out
#SBATCH --error  /Midgard/home/%u/Dermatology/logs/custom_eb6_incr_cosine.err
#SBATCH --job-name custom_eb6_incr_cosine

. ~/anaconda3/etc/profile.d/conda.sh
conda activate isic
python /Midgard/home/ferles/Dermatology/src/custom_train.py --c /Midgard/home/ferles/Dermatology/src/configs/Custom_ISIC/custom_EfficientNetB6_incr_cosine.json