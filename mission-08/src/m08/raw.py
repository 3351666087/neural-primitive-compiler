"""Third-party raw files for Mission 08: location, pinned source and SHA-256 (data/README.md). Nothing here is committed
to git; `fetch` re-downloads a missing file from its pinned commit and every `path` call checks the hash.
  python3 -I -m m08.raw check        # verify all present files
  python3 -I -m m08.raw fetch        # download missing files, then verify
"""

from __future__ import annotations

import hashlib
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"

CECT = "https://raw.githubusercontent.com/openworm/ConnectomeToolbox/2ba2ff11b0c9ce101003aaef3faf06527dc6f61c/cect/data/"
WNA = "https://raw.githubusercontent.com/francescorandi/wormneuroatlas/b2e13d88b670efcb3438aeacba2ad4bd6c383933/wormneuroatlas/data/"
NEMA = "https://nemanode.org/api/download-connectivity?datasetId="        # unversioned API: the hash is the version
RANDI = "https://static-content.springer.com/esm/art%3A10.1038%2Fs41586-023-06683-4/MediaObjects/"
PATHAK = "https://journals.plos.org/ploscompbiol/article/file?type=supplementary&id=10.1371/journal.pcbi.1007602."
SKU = "https://raw.githubusercontent.com/bluevex/elegans-atlas/main/"
BRITTIN = "https://zenodo.org/api/records/4383277/files/"
RS = "https://raw.githubusercontent.com/schneidmanlab/BrainBuildingPaper/d762ed07597efcc70c3963eac5abec672f4443d4/CElegansData/"
FLYVIS = "https://raw.githubusercontent.com/TuragaLab/flyvis/main/flyvis/connectome/"   # hash is the version
EDMOND = "https://edmond.mpg.de/api/access/datafile/"
EDMOND_ID = {"fig3_Mi1.npy": 104811, "fig3_Tm3.npy": 104816, "fig3_Mi4.npy": 104812, "fig3_Mi9.npy": 104813,
             "fig3_C3.npy": 104809, "fig3_led.npy": 104810, "fig3_T4v.npy": 104815, "fig3_T4r.npy": 104814,
             "fig4_T4_vm_gfp.npy": 104820, "fig4_T4_vm_gluclarnai.npy": 104821, "fig4_T4_rin_gfp.npy": 104818,
             "fig4_T4_rin_gluclarnai.npy": 104819}

# key: (directory, file name, source URL prefix, SHA-256)
FILES = {
    "witvliet_1": ("cect_2026", "witvliet_2020_1 L1.xlsx", CECT, "e988deaa25d290786434a23131c1bf3f144e3ca07980233a6edbfcfb8d4d30be"),
    "witvliet_2": ("cect_2026", "witvliet_2020_2 L1.xlsx", CECT, "b365bdd96dea52c261c748232dd5d333671721865be1282f3b7efa806d010e2a"),
    "witvliet_3": ("cect_2026", "witvliet_2020_3 L1.xlsx", CECT, "d94d522af2a64177ebef0dea0951b2a252eb973bbed01a85a19aaafe4ff0244b"),
    "witvliet_4": ("cect_2026", "witvliet_2020_4 L1.xlsx", CECT, "10f16bd1f122288e9111acabccbf3fbd4811b861ce6e3293600d4eb5e42e4fbe"),
    "witvliet_5": ("cect_2026", "witvliet_2020_5 L2.xlsx", CECT, "011ebda64c379fa066254ddd5c8ff0ab89621e1e85e8d31ffc0b37b9602fc163"),
    "witvliet_6": ("cect_2026", "witvliet_2020_6 L3.xlsx", CECT, "9b342751812bf42733ae7c0de8b40f41ea0af0c5c560215d59525631b220b177"),
    "witvliet_7": ("cect_2026", "witvliet_2020_7 adult.xlsx", CECT, "d0fd2dd32adbe5f04ce90a2e5b74c01c9a831876527b0a2b8bd5b94edc86b037"),
    "witvliet_8": ("cect_2026", "witvliet_2020_8 adult.xlsx", CECT, "fdead89606257c1b26e57069fbe1de14c7696633b75b59b79e74c0bcc3497e62"),
    "cook_2019": ("cect_2026", "SI 5 Connectome adjacency matrices, corrected July 2020.xlsx", CECT,
                  "1f4fdbf84746b69b49a8da0816f52787860ce349b638dce37924ba80f90c70c9"),
    "brittin_2021": ("cect_2026", "41586_2021_3284_MOESM5_ESM.xlsx", CECT, "b5c08b46971422e2bc22449e271592745e3ab21ea50ade6c77bd1cffacd62c7a"),
    "wormatlas_names": ("cect_2026", "IndividualNeurons.csv", CECT, "b69c0e994270493535994a69a47210dda04319592697eec2f4a65a9df8886195"),
    "cell_info": ("cect_2026", "all_cell_info.csv", CECT, "63c6fc5f55c90df092b24afe1cbfc96da63f577288e74621d6395fc195e6221d"),
    "neuron_tables": ("cect_2026", "CElegansNeuronTables.xls", CECT, "e6e2d51cd6a056c6058ec163bf6020d1a43a0a8d48719f09dddd8687c3956d74"),
    "funatlas": ("wormneuroatlas_0.0.7.3", "funatlas.h5", WNA, "53a99055667b853e1d3d6be573ec2613d38c9f6989f302ec38ecd38dd50c7975"),
    "wna_positions": ("wormneuroatlas_0.0.7.3", "anatlas_neuron_positions.txt", WNA,
                      "b854b039929185f22dcb2eadce24b08408bfdec80f1a88581fe33edb382ede40"),
    "wna_lineage": ("wormneuroatlas_0.0.7.3", "cell_lineage.txt", WNA, "d1f22fd7cdf125bf515e4c399f040319103139c34c4425a3c0e8411cddb3e840"),
    "wna_neuron_ids": ("wormneuroatlas_0.0.7.3", "neuron_ids.txt", WNA, "e2c7e54af611c1e85aa0705588fcf096ede5f0c28f7fd1d5f0cbec5480b786cc"),
    "wna_ganglia": ("wormneuroatlas_0.0.7.3", "aconnectome_ids_ganglia.json", WNA,
                    "e754fcb703b39b5f0db977d0b654ba2ac5ce09111f4e19aef3a85fb09ee2e0a2"),
    # NemaNode (fetched 2026-10-25): Witvliet 1-8 and White 1986 JSH (L4) / N2U (adult), chemical + electrical
    "nema_witvliet_1": ("nemanode_20261025", "witvliet_2020_1.json", NEMA, "d084b11040b4c1a05a873ad7e3d02b94be9e3f2ae19af6ded8f058e86d6b55bc"),
    "nema_witvliet_2": ("nemanode_20261025", "witvliet_2020_2.json", NEMA, "022c5c79cd3f16ecadd7155c5d9aac7f21c686bd5c38a374f61ea86f37a53953"),
    "nema_witvliet_3": ("nemanode_20261025", "witvliet_2020_3.json", NEMA, "45fa1eebfa4a13be3f295b9d4460dc0309faa04736c1ab5ee470a549f03a9f03"),
    "nema_witvliet_4": ("nemanode_20261025", "witvliet_2020_4.json", NEMA, "6e5e5147c3a878e21645d9d797fdac796470dd5d1284103490e7f197d5800fe5"),
    "nema_witvliet_5": ("nemanode_20261025", "witvliet_2020_5.json", NEMA, "155a590ce1f96a9de339f15e9e2def60e8d7be133ef173d9698ca6eff227b34f"),
    "nema_witvliet_6": ("nemanode_20261025", "witvliet_2020_6.json", NEMA, "8ae848f5c97b7ac126823b634f197234aff03487c36c57c1464baddb67f47d34"),
    "nema_witvliet_7": ("nemanode_20261025", "witvliet_2020_7.json", NEMA, "6bef7b6c8ea52009801d4e1502218177131375ed3275f9141a2faed14291915a"),
    "nema_witvliet_8": ("nemanode_20261025", "witvliet_2020_8.json", NEMA, "5aa27719ccea5f5ab4d19536d1093fa97c57984df0b878cad939e137c7fa8457"),
    "nema_white_jsh": ("nemanode_20261025", "white_1986_jsh.json", NEMA, "654da321936cbbdcc688eec646b1c13cb28c56d6a118e8e6c21c96bfb2524548"),
    "nema_white_n2u": ("nemanode_20261025", "white_1986_n2u.json", NEMA, "767770879acda9ee11ed05a95f70804eb67c0d21663acb18b3052a29eacad8b6"),
    "nema_cells": ("nemanode_20261025", "cells.json", "https://nemanode.org/api/", "377450f69955470aaeb6734ea5ac65d4062d281d67747e3487aab612107e2b10"),
    "nema_datasets": ("nemanode_20261025", "datasets.json", "https://nemanode.org/api/",
                      "8ae806f6fa9e5b742bca5f02b68415f6732f0974d2a6625cb4bc60a7a9ce90ad"),
    # Randi et al. 2023 Source Data (CC BY 4.0): Fig. 2 (WT), Fig. 3 (anatomy model), Extended Data Fig. 7 (unc-31)
    "randi_fig2": ("randi_2023_esm", "41586_2023_6683_MOESM5_ESM.xlsx", RANDI, "f02c68c9a2d34fe7b5aa8c7d74d8aca9ea9676d647e794ba99abbbff1b6350e5"),
    "randi_fig3": ("randi_2023_esm", "41586_2023_6683_MOESM6_ESM.xlsx", RANDI, "50679b566ad10a46d109543423ccb07f3ba481464079f42ae7b3ddf6e3f7e929"),
    "randi_ed7": ("randi_2023_esm", "41586_2023_6683_MOESM15_ESM.xlsx", RANDI, "534e6ddf5eae2b307854716de8336066be95349b1fa127248984f273d9ff2837"),
    # Pathak et al. 2020 S5 Table (CC BY 4.0): birth times transcribed from Sulston's lineages
    "pathak_s5": ("pathak_2020_si", "pcbi.1007602.s021.xls", PATHAK, "7389fcffc5c3f11df20e1a8443623ab281b548b304e530983fafee867f3247a7"),
    # Skuhersky et al. 2022 atlas (paper CC BY 4.0; repository without licence)
    "sku_lowres": ("skuhersky_2022", "LowResAtlas.csv", SKU, "9a958a764b6dbec03fd433b45cb6456edc524f62b2d45c62cbe4ee2877121c67"),
    "sku_hires": ("skuhersky_2022", "LowResAtlasWithHighResHeadsAndTails.csv", SKU,
                  "bb45477c58f1a6a920fb7a9dcf800bd1d0b2c0e347311fa6745eed6c923f49d7"),
    # Brittin et al. 2021 contactome (Zenodo 4383277, CC BY 4.0); the archive is extracted into adjacency_x/
    "brittin_adjacency": ("brittin_2021_zenodo4383277", "adjacency.tar.bz2", BRITTIN,
                          "06b19d6218e8d53b4b307140a3864a1051345cd1e3ba704b62703b704055935a"),
    # Richter & Schneidman 2025 repository inputs (no licence; used only to check that our inputs match theirs)
    "rs_positions": ("brainbuilding_d762ed07", "NeuronPosition3D.csv", RS, "38ba746590b342a0cf93c6074fb26eb8e2eea6188e1303fda7d63dcf5924c67e"),
    "rs_birth": ("brainbuilding_d762ed07", "time_of_birth.xls", RS, "92b6e1ea2ca8c225e563a25b0ddbf1961ff5ab7606fe393eca10898f24a8a8c4"),
    "rs_celltypes": ("brainbuilding_d762ed07", "CellTypes.xlsx", RS, "cf442a285c43f6fd95fbaa6b50b3e0696187cdf39242377d95a5446354ae2244"),
    "rs_synapses": ("brainbuilding_d762ed07", "synapse_count_matrices.xlsx", RS,
                    "bd725d1f6121abeb8ec08d0b80edad94d9e0fea954a8704ee07c7f4be7cebfe6"),
    # flyvis 1.2.0 (MIT): consensus connectome and literature labels
    "flyvis_connectome": ("flyvis_1.2.0", "fib25-fib19_v2.2.json", FLYVIS,
                          "bfbb0766251ff09e22723d0ebbf7b14793e70b3ae8ad0eea64eac9d28223351a"),
    "flyvis_labels": ("flyvis_1.2.0", "groundtruth_utils.py.txt", FLYVIS + "../utils/",
                      "fe3927cbfc5463abf2dfefd590b8b628a7f3be11c9a079a6bd0de70d5241dae6"),
    # Groschner et al. 2022 (Edmond doi:10.17617/3.8G, CC BY 4.0): input neurons (development); T4 files are held out
    "groschner_Mi1": ("groschner_2022_edmond", "fig3_Mi1.npy", EDMOND, "351e9e791a30d1c5bac329165934fbc05dbcfbb038b4b6e940e2531de1d61cce"),
    "groschner_Tm3": ("groschner_2022_edmond", "fig3_Tm3.npy", EDMOND, "07797ccd2ce72d3ea89c9ca01ba641c7c92d3d6dd198d6324596f2cf16b0fb82"),
    "groschner_Mi4": ("groschner_2022_edmond", "fig3_Mi4.npy", EDMOND, "9309bb6deadcb8bf5c9a52267ef6564c314a04212af81c129b0754cf4de1f791"),
    "groschner_Mi9": ("groschner_2022_edmond", "fig3_Mi9.npy", EDMOND, "3d5909c9b6c42776ff5e56d7219eacd002758a24b3cf5b7cecf30a07b8bf5c83"),
    "groschner_C3": ("groschner_2022_edmond", "fig3_C3.npy", EDMOND, "b9118e32cfb0d22acd4da41aee6931923ea33e4dda258df2abd26fd252e21be6"),
    "groschner_led": ("groschner_2022_edmond", "fig3_led.npy", EDMOND, "8d158e5a2abee4cbc77ccc7eda7b77cac31550dd3a20a2142638e7c257ca734b"),
}

# URL suffix overrides where the remote name differs from the local file name
REMOTE = {
    **{f"nema_witvliet_{k}": f"witvliet_2020_{k}" for k in range(1, 9)},
    "nema_white_jsh": "white_1986_jsh", "nema_white_n2u": "white_1986_n2u", "nema_cells": "cells", "nema_datasets": "datasets",
    "pathak_s5": "s021", "brittin_adjacency": "adjacency.tar.bz2/content", "flyvis_labels": "groundtruth_utils.py",
    **{f"groschner_{k}": str(EDMOND_ID[f"fig3_{k}.npy"]) for k in ("Mi1", "Tm3", "Mi4", "Mi9", "C3", "led")},
}

_CHECKED = set()


def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def path(key):
    """Path of a verified raw file for reading; held-out files only for the judge after the freeze (custody.allow)."""
    from . import custody
    custody.allow(key)
    return _verified(key)


def _verified(key):
    d, name, _, digest = FILES[key]
    p = RAW / d / name
    if key not in _CHECKED:
        if not p.exists():
            raise FileNotFoundError(f"{p} missing; run python3 -I -m m08.raw fetch")
        got = sha256(p)
        if got != digest:
            raise ValueError(f"{p}: SHA-256 {got} != {digest}")
        _CHECKED.add(key)
    return p


def fetch():
    for key, (d, name, base, _) in FILES.items():
        p = RAW / d / name
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(base + (REMOTE.get(key) or urllib.parse.quote(name)), p)
        _verified(key)


def main(argv):
    if argv[1:] == ["fetch"]:
        fetch()
    for key in FILES:                       # hash check only; held-out contents are not parsed here
        print(key, "ok" if _verified(key) else "")


if __name__ == "__main__":
    main(sys.argv)
