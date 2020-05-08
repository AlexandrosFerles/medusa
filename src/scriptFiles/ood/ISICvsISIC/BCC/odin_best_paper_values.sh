#!/usr/bin/env bash
#SBATCH --mem  10GB
#SBATCH --gres gpu:1
#SBATCH --cpus-per-task 1
#SBATCH --mail-type END
#SBATCH --mail-type FAIL
#SBATCH --mail-user ferles@kth.se
#SBATCH --output /Midgard/home/%u/Dermatology/logs/odin_BCC_best_paper.out
#SBATCH --error  /Midgard/home/%u/Dermatology/logs/odin_BCC_best_paper.err
#SBATCH --job-name odin_BCC_best_paper

. ~/anaconda3/etc/profile.d/conda.sh
conda activate isic
python ood.py --ood_method odin \
              --num_classes 7 \
              --in_distribution_dataset ISIC \
              --out_distribution_dataset ISIC \
              --model_checkpoint custom_exclude_BCC_step_lr_cutout_eb0-best-balanced-accuracy-model.pth \
              --exclude_class BCC \
              --temperature 1000 \
              --epsilon 0.0014 > results/txts/ISICvsISIC/BCC/odin_best_paper_BCC.txt