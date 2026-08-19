# Stage the ohc_derive synthetic-level blobs, then package each into its OHCA/OHU deliverable.
# One blob per synthetic level (derive_<tag>_<level>.nc); the emitter writes one file each.
for level in 0_300 0_700 700_2000 0_2000
do
  cp /scratch/alpine/wimi7695/validation/derive_validation_${level}.nc data/.
done

sbatch emit.slurm
