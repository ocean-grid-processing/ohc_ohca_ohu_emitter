for level in 15_20 15_300 300_700 700_1850 1800_1850
do
  cp /scratch/alpine/wimi7695/validation/argo_ohc_Global_2004_2024_${level}/derive_LocalGP_2004_2024_lev${level}.nc data/.
done

sbatch combine.slurm
