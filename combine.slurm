#!/bin/bash
#SBATCH --qos=preemptable
#SBATCH --export=NONE
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --time=12:00:00
#SBATCH --job-name=ohc_combine
#SBATCH --output=%x.%j.out
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=katie.mills@colorado.edu
#SBATCH --mem=64GB
#SBATCH --exclude=blanca-g6-u21

module purge
module load anaconda/2023.09
conda activate ohc_crosscheck

cd $SLURM_SUBMIT_DIR
python combine.py /scratch/alpine/wimi7695/ohc_prod/results/derive_${1}-ohca-ohu_2004_2025_lev* --tag $1 --provenance-link https://github.com/argovis/ohc_ohca_ohu_emitter/releases/tag/$1 \
  --levels 0_300,0_700,0_1000,700_2000,0_2000 --time-window 2005:2024


