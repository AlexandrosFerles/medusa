#!/usr/bin/env bash
#SBATCH --mem  12GB
#SBATCH --gres gpu:2
#SBATCH --cpus-per-task 2
#SBATCH --mail-type FAIL
#SBATCH --mail-user ferles@kth.se
#SBATCH --output /Midgard/home/%u/Dermatology/logs/efficientNetB6-5-fold-step-lr-auto-cutout.out
#SBATCH --error  /Midgard/home/%u/Dermatology/logs/efficientNetB6-5-fold-step-lr-auto-cutout.err
#SBATCH --job-name EB6-5-fold-step-lr-auto-cutout

. ~/anaconda3/etc/profile.d/conda.sh
conda activate isic
python ../train.py --config configs/ISIC/EfficientNetB6.json