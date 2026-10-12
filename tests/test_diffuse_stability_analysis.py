"""Proposal matching must survive native path compaction/reordering."""
import importlib.util
from pathlib import Path
import numpy as np

spec=importlib.util.spec_from_file_location('diffuse_audit',Path(__file__).resolve().parents[1]/'scripts/qualify_diffuse_stability.py')
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)


def test_matches_translated_launch_rays_after_path_permutation():
    points=np.array([[0.,0,0],[3.,2,0],[-4.,1,0]])
    endpoints=np.array([[-5.,0,10],[5.,0,10]])
    delta=np.array([.03,0,0]);moved=endpoints.copy();moved[0]+=delta
    left,right=audit.match_proposals(points,(points+delta)[[2,0,1]],endpoints,moved)
    np.testing.assert_array_equal(left,[0,1,2])
    np.testing.assert_array_equal(right,[1,2,0])


def test_rejects_unrelated_proposals():
    points=np.array([[0.,0,0],[3.,2,0],[-4.,1,0]])
    endpoints=np.array([[-5.,0,10],[5.,0,10]])
    left,right=audit.match_proposals(points,points+[0,20,0],endpoints,endpoints)
    assert len(left)==len(right)==0
