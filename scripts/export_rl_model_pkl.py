"""
Export SHARP RL Model Checkpoint from NPZ to PKL format for Hardware/Pi Deployment.
"""

import os
import pickle
import numpy as np
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def convert_npz_to_pkl(npz_path: Path, output_pkl_path: Path):
    print(f"[+] Loading NPZ model checkpoint: {npz_path}")
    if not npz_path.exists():
        raise FileNotFoundError(f"Checkpoint file not found: {npz_path}")
    
    data = np.load(npz_path, allow_pickle=False)
    
    # Store all dictionary arrays into standard Python/NumPy dictionary for pickle
    model_dict = {key: data[key] for key in data.files}
    
    # Metadata for hardware team
    model_dict['meta'] = {
        'model_name': 'SHARP Branching Dueling Q-Network (BDQ v2)',
        'architecture': '305-feature input -> 256 hidden layer -> 28 branches x 3 levels',
        'n_branches': 28,
        'n_levels': 3,
        'features_input': 305,
        'exported_at': '2026-09-18',
        'level_names': {0: 'SHED', 1: 'ON', 2: 'REDUCED'}
    }
    
    print(f"[+] Saving PKL model file to: {output_pkl_path}")
    output_pkl_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_pkl_path, 'wb') as f:
        pickle.dump(model_dict, f, protocol=pickle.HIGHEST_PROTOCOL)
        
    print(f"[SUCCESS] Exported PKL model successfully! Size: {output_pkl_path.stat().st_size / 1024:.2f} KB")

def main():
    model_dir = ROOT / "models" / "sharp_bdq_v2"
    npz_file = model_dir / "checkpoint.npz"
    pkl_file = model_dir / "sharp_rl_model.pkl"
    
    convert_npz_to_pkl(npz_file, pkl_file)
    
    # Also save a copy in root models/ for easy access by hardware team
    root_pkl = ROOT / "models" / "sharp_rl_model.pkl"
    convert_npz_to_pkl(npz_file, root_pkl)

if __name__ == '__main__':
    main()
