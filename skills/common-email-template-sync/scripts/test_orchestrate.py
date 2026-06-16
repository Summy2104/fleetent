"""Unit tests for orchestrate_email_sync.py"""
import subprocess
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

# 将 scripts/ 目录加入 sys.path，使 orchestrate_email_sync 可被 import
# 只需执行一次（模块级），避免在每个 setUp 中重复插入
sys.path.insert(0, str(Path(__file__).parent))


class TestClassifyResult(unittest.TestCase):
    def test_success(self):
        import orchestrate_email_sync as orch
        self.assertEqual(orch.classify_result("✅ 模版同步完成：模版A"), "✅")

    def test_skipped(self):
        import orchestrate_email_sync as orch
        self.assertEqual(orch.classify_result("⏭️ 跳过：模版A（md5 一致，无变化）"), "⏭️")

    def test_failure_unknown_output(self):
        import orchestrate_email_sync as orch
        self.assertEqual(orch.classify_result("something unexpected"), "❌")

    def test_failure_empty_string(self):
        import orchestrate_email_sync as orch
        self.assertEqual(orch.classify_result(""), "❌")


class TestBuildSlackMessage(unittest.TestCase):
    def test_all_success_shows_counts(self):
        import orchestrate_email_sync as orch
        t = datetime(2026, 4, 15, 10, 5)
        msg = orch.build_slack_message(t, 30, ["模版A", "模版B"], [], [])
        self.assertIn("✅ 成功：2 个", msg)
        self.assertIn("⏭️ 跳过：0 个", msg)
        self.assertIn("❌ 失败：0 个", msg)
        self.assertIn("模版A", msg)
        self.assertIn("模版B", msg)

    def test_with_failures_shows_error_detail(self):
        import orchestrate_email_sync as orch
        t = datetime(2026, 4, 15, 10, 5)
        msg = orch.build_slack_message(t, 30, [], [], [("模版C", "pandoc error")])
        self.assertIn("❌ 失败：1 个", msg)
        self.assertIn("模版C", msg)
        self.assertIn("pandoc error", msg)

    def test_all_skipped_no_converted_section(self):
        import orchestrate_email_sync as orch
        t = datetime(2026, 4, 15, 10, 5)
        msg = orch.build_slack_message(t, 10, [], ["模版A"], [])
        self.assertIn("⏭️ 跳过：1 个", msg)
        self.assertNotIn("已转换", msg)

    def test_elapsed_seconds_included(self):
        import orchestrate_email_sync as orch
        t = datetime(2026, 4, 15, 10, 5)
        msg = orch.build_slack_message(t, 42, [], [], [])
        self.assertIn("42s", msg)


class TestCallAgent(unittest.TestCase):
    @patch("orchestrate_email_sync.subprocess.run")
    def test_returns_stdout_text(self, mock_run):
        import orchestrate_email_sync as orch
        mock_run.return_value = MagicMock(
            stdout="✅ 模版同步完成：模版A\n",
            returncode=0,
        )
        result = orch.call_agent("同步邮件模版 模版A --file-id abc123")
        self.assertEqual(result, "✅ 模版同步完成：模版A")

    @patch("orchestrate_email_sync.subprocess.run")
    def test_invokes_fleetent_agent_run(self, mock_run):
        import orchestrate_email_sync as orch
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        orch.call_agent("扫描邮件模版")
        cmd = mock_run.call_args[0][0]
        self.assertIn("fleetent", cmd)
        self.assertIn("agent", cmd)
        self.assertIn("run", cmd)
        self.assertIn("扫描邮件模版", cmd)

    @patch("orchestrate_email_sync.subprocess.run")
    def test_raises_on_subprocess_error(self, mock_run):
        import orchestrate_email_sync as orch
        mock_run.side_effect = subprocess.CalledProcessError(1, "fleetent", stderr="err")
        with self.assertRaises(subprocess.CalledProcessError):
            orch.call_agent("扫描邮件模版")


class TestSendSlack(unittest.TestCase):
    @patch("orchestrate_email_sync.subprocess.run")
    def test_delegates_to_agent_send_im_message(self, mock_run):
        import orchestrate_email_sync as orch
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        orch.send_slack("hello world", "C123456")
        cmd = mock_run.call_args[0][0]
        # send_slack 通过 fleetent agent run 让 agent 用 send_im_message 投递
        self.assertIn("fleetent", cmd)
        self.assertIn("agent", cmd)
        self.assertIn("run", cmd)
        # 频道与消息体作为指令文本传给 agent
        agent_message = next(a for a in cmd if "hello world" in a)
        self.assertIn("C123456", agent_message)
        self.assertIn("send_im_message", agent_message)


class TestPreflight(unittest.TestCase):
    @patch.dict("os.environ", {
        "SLACK_NOTIFY_CHANNEL": "C123",
        "HOST_MEDIA_DIR": "/tmp/ws/bs-intern/media",
    })
    @patch("orchestrate_email_sync.shutil.which", return_value="/usr/bin/fleetent")
    def test_returns_channel_path_when_env_complete(self, _):
        import orchestrate_email_sync as orch
        channel, path = orch.preflight()
        self.assertEqual(channel, "C123")
        self.assertEqual(path, "/usr/bin/fleetent")

    @patch.dict("os.environ", {}, clear=True)
    @patch("orchestrate_email_sync.shutil.which", return_value=None)
    def test_exits_when_required_env_missing(self, _):
        import orchestrate_email_sync as orch
        with self.assertRaises(SystemExit):
            orch.preflight()

    @patch.dict("os.environ", {
        "SLACK_NOTIFY_CHANNEL": "C123",
        "HOST_MEDIA_DIR": "/tmp/ws/bs-intern/media",
    })
    @patch("orchestrate_email_sync.shutil.which", return_value=None)
    def test_exits_when_fleetent_not_found(self, _):
        import orchestrate_email_sync as orch
        with self.assertRaises(SystemExit):
            orch.preflight()



if __name__ == "__main__":
    unittest.main()
