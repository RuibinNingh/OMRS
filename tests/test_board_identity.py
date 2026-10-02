"""展示板引用跨移动、归档、UID复用仍绑定原题身份。"""
import tempfile
import unittest

from omrs.boards import add_items, board_items_for_export, create_board, get_board, list_boards, remove_items
from omrs.creation import create_question
from omrs.data_repository import IdentityConflict
from omrs.question_ops import delete_question, move_question


class BoardIdentityTests(unittest.TestCase):
    def test_archived_reference_never_falls_back_to_reused_uid(self):
        with tempfile.TemporaryDirectory() as vault:
            original = create_question(vault,'数学','集合',5,question_text='original')
            board = create_board(vault,'old',[{'question_id':original['question_id']}])
            delete_question(vault,original['uid'])
            new = create_question(vault,'数学','集合',5,question_text='new')
            self.assertEqual(new['uid'],original['uid'])
            item = get_board(vault,board['id'])['items'][0]
            self.assertTrue(item['missing'])
            self.assertEqual(item['question_id'],original['question_id'])
            self.assertEqual(board_items_for_export(vault,board['id'])[1],[])
            added = add_items(vault,board['id'],[{'question_id':new['question_id']}])
            self.assertEqual(added['added_question_ids'],[new['question_id']])
            self.assertEqual(list_boards(vault)[0]['question_ids'],[original['question_id'],new['question_id']])

    def test_current_uid_remove_after_move_cannot_remove_reused_identity(self):
        with tempfile.TemporaryDirectory() as vault:
            old = create_question(vault,'数学','集合',5,question_text='old')
            board = create_board(vault,'board',[old['uid']])
            moved = move_question(vault,old['uid'],'数学','函数')
            new = create_question(vault,'数学','集合',5,question_text='new')
            add_items(vault,board['id'],[{'question_id':new['question_id']}])
            removed = remove_items(vault,board['id'],[moved['uid']])
            self.assertEqual([i['question_id'] for i in removed['items']],[new['question_id']])

    def test_supplied_identity_and_display_uid_conflict_is_rejected(self):
        with tempfile.TemporaryDirectory() as vault:
            a = create_question(vault,'数学','集合',5)
            b = create_question(vault,'数学','函数',5)
            board = create_board(vault,'board')
            with self.assertRaises(IdentityConflict):
                add_items(vault,board['id'],[{'question_id':a['question_id'],'uid':b['uid']}])
            self.assertEqual(get_board(vault,board['id'])['items'],[])


if __name__ == '__main__':
    unittest.main()
