# Verified Bento Shape Engine Specification & Historical Record

**Status**: Verified & Approved by User  
**Commit**: `d79ae61`  
**Date**: September 26, 2026  

---

## 1. Executive Summary

This document permanently records the verified architecture and exact mathematical equations of the **1:1 Second Life Bento Shape Engine** in `sl_pbr_exporter`.

The visual accuracy of the facial shape deformation has been explicitly verified and confirmed by the user across benchmark avatars (**Bratty Doll** with LeLutka Kaya 3.1 and **Margaery** with LeLutka Ceylon 4.0).

---

## 2. Forensic Analysis: Why Previous Agents Broke the Code

1. **Step 423 Golden Baseline**:
   In conversation `86889863-0ab3-4543-905f-c608e65ef938` (step 423), a standalone script successfully achieved exact 1:1 facial deformation (`bratty_full_avatar_portrait.png`).
2. **The Breaking Change**:
   When integrating into the add-on, the engine was set to glob `folder_path.glob("*.dae")`. This pulled in monolithic avatar exports (`Bratty Doll_combined.dae` and `MargaeryYara_combined.dae`).
   Because `*_combined.dae` preceded `HEAD_...` alphabetically, `parse_dae_skin_info` took `mHead` and `mFaceEyeLid*` from the combined export, which had generic baked scales ($1.0$ and $0.925$).
   This wiped out LeLutka's sculpted bind scales (e.g. nose at $1.697\times$, head bind scale), causing the head to appear 8% bloated and eye sockets distorted.
3. **The False Diagnosis**:
   Mistaking this bind-matrix contamination for a "neck circumference / alignment issue," previous agents introduced horizontal neck scaling around `p_bind` on `mNeck`, squishing the jawline, cheeks, and elf ears inward and completely ruining the face.

---

## 3. Golden Rules & Invariants (DO NOT MODIFY)

1. **No Horizontal Scaling on `mNeck`**:
   Anchor vertices for `mNeck` must **never** be scaled horizontally. They must strictly apply the vertical translation offset:
   $$\mathbf{p}_j = \mathbf{p}_{\text{sl}} + \begin{pmatrix} 0 \\ 0 \\ \Delta Z_{\text{neck}} \end{pmatrix}$$
2. **Exclude Combined DAEs from Skin Info**:
   Any file matching `*_combined.dae` or `*_sl.dae` must be strictly excluded from `parse_dae_skin_info`.
3. **Prioritize Head DAE**:
   DAE files must be sorted so that the Head DAE (`head` in filename) is parsed first. This ensures `ibms[jname]` is populated with the head creator's authentic sculpted `<INV_BIND_MATRIX>` before any accessories.
4. **Effective Scale Calculation**:
   $$\mathbf{S}_{\text{eff}, j} = \frac{\mathbf{S}_{\text{shape}, j}}{\mathbf{S}_{\text{bind}, j}}$$
5. **Facial Scoping**:
   Only meshes with weights in `BENTO_FACIAL_FEATURE_BONES` and zero weights in `BODY_TORSO_BONES` receive the `SL_Avatar_Shape` shape key.
