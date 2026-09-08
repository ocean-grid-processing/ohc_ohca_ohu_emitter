#!/bin/bash
#SBATCH --qos=preemptable
#SBATCH --export=NONE
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --time=00:30:00
#SBATCH --job-name=ohc_ohca_ohu
#SBATCH --output=%x.%j.out
#SBATCH --mail-type=FAIL
#SBATCH --mail-user=katie.mills@colorado.edu
#SBATCH --mem=8GB
#SBATCH --exclude=blanca-g6-u21

module purge
module load anaconda/2023.09
conda activate ohc_crosscheck

cd $SLURM_SUBMIT_DIR
tag=260824-OP20260507
results=/scratch/alpine/wimi7695/ohc_prod/results_260824
python emit.py \
  ${results}/derive_${tag}-ohca-ohu_0_2000.nc \
  --tag ${tag} \
  --provenance-link https://github.com/argovis/ohc_map_emitter/releases/tag/260824-OP20260507 \
  --out ${results}
