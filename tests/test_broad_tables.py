import unittest
from pathlib import Path
import cv2
import numpy as np

from broad_tables import result_matches_view, TableScanner


class BroadResultTest(unittest.TestCase):
    def desk(self):
        image=cv2.imread(str(Path(__file__).resolve().parents[1]/'evaluation/public-images/standing-desk.jpg'))
        self.assertIsNotNone(image)
        return image

    def test_person_motion_outside_visible_table_does_not_invalidate_it(self):
        image=self.desk();current=image.copy();current[:400]=0
        self.assertFalse(result_matches_view(image,current,14,[(30,420,200,500)]))
        self.assertTrue(result_matches_view(image,current,14,[(30,420,200,500)],people=[(0,0,image.shape[1],400)]))

    def test_masking_people_cannot_hide_a_table_change_or_camera_turn(self):
        image=self.desk();current=image.copy();current[420:500,30:200]=0
        self.assertFalse(result_matches_view(image,current,14,[(30,420,200,500)],people=[(0,0,200,200)]))
        self.assertFalse(result_matches_view(image,cv2.rotate(image,cv2.ROTATE_180),14,[(30,420,200,500)],people=[(0,0,200,200)]))

    def test_almost_fully_occluded_table_has_no_reusable_evidence(self):
        image=self.desk()
        self.assertFalse(result_matches_view(image,image.copy(),14,[(30,420,200,500)],people=[(25,410,210,510)]))
        self.assertFalse(result_matches_view(image,image.copy(),14,[(30,420,200,500)],people=[(0,0,image.shape[1],image.shape[0])]))

    def test_changed_proposal_does_not_discard_an_independent_unchanged_one(self):
        import time
        image=self.desk();current=image.copy();current[153:769,48:432]=0
        scanner=TableScanner.__new__(TableScanner);scanner.status='unavailable';scanner.busy=False
        scanner.result=(image,time.time()-14,[{'box':(48,153,432,769)},{'box':(528,845,864,1384)}],1000,())
        items,scan=scanner.update(current,time.time(),people=())
        self.assertEqual([item['box'] for item in items],[(528,845,864,1384)])
        self.assertTrue(scan['matched'])

    def test_static_closeup_can_match_without_background_outside_the_table(self):
        image=self.desk();h,w=image.shape[:2]
        self.assertTrue(result_matches_view(image,image.copy(),14,[(0,0,w,h)]))

    def test_changed_or_old_view_cannot_reuse_table_boxes(self):
        image = cv2.imread(str(Path(__file__).resolve().parents[1] / 'evaluation/public-images/standing-desk.jpg'))
        self.assertIsNotNone(image)
        self.assertTrue(result_matches_view(image, image.copy(), 4))
        self.assertFalse(result_matches_view(image, cv2.rotate(image, cv2.ROTATE_180), 4))
        self.assertFalse(result_matches_view(image, np.zeros_like(image), 4))
        self.assertFalse(result_matches_view(image, image, 31))

    def test_changed_small_table_region_invalidates_a_similar_overall_view(self):
        image = cv2.imread(str(Path(__file__).resolve().parents[1] / 'evaluation/public-images/standing-desk.jpg'))
        current = image.copy()
        box = (30,420,200,500)
        current[420:500,30:200] = 0
        self.assertTrue(result_matches_view(image, current, 4))
        self.assertFalse(result_matches_view(image, current, 4, [box]))


if __name__ == '__main__':
    unittest.main()
