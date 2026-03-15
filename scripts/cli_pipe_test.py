"""Wave 0: Claude CLI PIPE mode verification script.

Tests whether claude CLI works correctly when stdin/stdout are pipes (not TTY).
This is the GO/NO-GO decision point for the entire CSM architecture.
"""

import asyncio
import sys
import time


async def test_pipe_spawn():
    """Test 1: Can claude CLI start with PIPE stdin/stdout?"""
    print("=" * 60)
    print("TEST 1: PIPE mode spawn")
    print("=" * 60)

    try:
        proc = await asyncio.create_subprocess_exec(
            "claude", "-p", "--output-format", "json",
            "--verbose", "say hello in exactly 3 words",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
        print(f"Exit code: {proc.returncode}")
        print(f"Stdout ({len(stdout)} bytes):")
        print(stdout.decode("utf-8", errors="replace")[:2000])
        if stderr:
            print(f"Stderr ({len(stderr)} bytes):")
            print(stderr.decode("utf-8", errors="replace")[:500])
        return proc.returncode == 0
    except asyncio.TimeoutError:
        print("TIMEOUT after 60s")
        return False
    except Exception as e:
        print(f"ERROR: {e}")
        return False


async def test_interactive_pipe():
    """Test 2: Can we spawn interactive claude and send input via stdin?"""
    print("\n" + "=" * 60)
    print("TEST 2: Interactive PIPE mode")
    print("=" * 60)

    try:
        proc = await asyncio.create_subprocess_exec(
            "claude",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        # Wait a bit for startup
        await asyncio.sleep(3)

        # Check if process is still running
        if proc.returncode is not None:
            stdout = await proc.stdout.read()
            stderr = await proc.stderr.read()
            print(f"Process exited immediately with code: {proc.returncode}")
            print(f"Stdout: {stdout.decode('utf-8', errors='replace')[:1000]}")
            print(f"Stderr: {stderr.decode('utf-8', errors='replace')[:1000]}")
            return False

        # Try sending input
        print("Process running, sending 'hello' via stdin...")
        proc.stdin.write(b"hello\n")
        await proc.stdin.drain()

        # Read output with timeout
        output_lines = []
        try:
            while True:
                line = await asyncio.wait_for(proc.stdout.readline(), timeout=30)
                if not line:
                    break
                decoded = line.decode("utf-8", errors="replace")
                output_lines.append(decoded)
                print(f"  > {decoded.rstrip()}")
                if len(output_lines) > 20:
                    break
        except asyncio.TimeoutError:
            print(f"  (timeout after reading {len(output_lines)} lines)")

        # Send /exit to quit
        try:
            proc.stdin.write(b"/exit\n")
            await proc.stdin.drain()
            await asyncio.wait_for(proc.wait(), timeout=10)
        except Exception:
            proc.terminate()
            await asyncio.wait_for(proc.wait(), timeout=5)

        print(f"Total lines captured: {len(output_lines)}")
        return len(output_lines) > 0

    except Exception as e:
        print(f"ERROR: {e}")
        return False


async def test_stream_json():
    """Test 3: stream-json output format (verified to work in --print mode)."""
    print("\n" + "=" * 60)
    print("TEST 3: stream-json output (--print mode)")
    print("=" * 60)

    try:
        proc = await asyncio.create_subprocess_exec(
            "claude", "-p",
            "--output-format", "stream-json",
            "--verbose",
            "respond with exactly: OK",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
        output = stdout.decode("utf-8", errors="replace")

        # Parse JSON lines
        import json
        events = []
        for line in output.strip().split("\n"):
            if line.strip():
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    print(f"  Non-JSON line: {line[:100]}")

        print(f"Total events: {len(events)}")
        for evt in events:
            evt_type = evt.get("type", "unknown")
            subtype = evt.get("subtype", "")
            if evt_type == "result":
                print(f"  {evt_type}: cost=${evt.get('total_cost_usd', 'N/A')}, "
                      f"tokens_in={evt.get('usage', {}).get('input_tokens', 'N/A')}, "
                      f"tokens_out={evt.get('usage', {}).get('output_tokens', 'N/A')}")
            elif evt_type == "system" and subtype == "init":
                print(f"  {evt_type}/{subtype}: session_id={evt.get('session_id', 'N/A')[:8]}...")
            else:
                print(f"  {evt_type}/{subtype}")

        return proc.returncode == 0 and len(events) > 0

    except Exception as e:
        print(f"ERROR: {e}")
        return False


async def test_resume():
    """Test 4: --resume flag in PIPE mode."""
    print("\n" + "=" * 60)
    print("TEST 4: --resume in PIPE mode")
    print("=" * 60)

    # First, get a session ID from a --print call
    try:
        proc = await asyncio.create_subprocess_exec(
            "claude", "-p",
            "--output-format", "stream-json",
            "--verbose",
            "remember the number 42",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=60)

        import json
        session_id = None
        for line in stdout.decode().strip().split("\n"):
            try:
                evt = json.loads(line)
                if "session_id" in evt:
                    session_id = evt["session_id"]
            except json.JSONDecodeError:
                pass

        if not session_id:
            print("Could not get session_id")
            return False

        print(f"Got session_id: {session_id[:8]}...")

        # Resume with that session
        proc2 = await asyncio.create_subprocess_exec(
            "claude", "-p",
            "--resume", session_id,
            "--output-format", "stream-json",
            "--verbose",
            "what number did I ask you to remember?",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout2, _ = await asyncio.wait_for(proc2.communicate(), timeout=60)

        result_text = ""
        for line in stdout2.decode().strip().split("\n"):
            try:
                evt = json.loads(line)
                if evt.get("type") == "result":
                    result_text = evt.get("result", "")
            except json.JSONDecodeError:
                pass

        print(f"Resume result: {result_text[:200]}")
        return "42" in result_text

    except Exception as e:
        print(f"ERROR: {e}")
        return False


async def main():
    print("Claude CLI PIPE Mode Verification")
    print("=" * 60)
    print()

    results = {}

    results["pipe_spawn"] = await test_pipe_spawn()
    results["interactive_pipe"] = await test_interactive_pipe()
    results["stream_json"] = await test_stream_json()
    results["resume"] = await test_resume()

    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)
    for test, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {test}: {status}")

    # GO/NO-GO decision
    critical = results["pipe_spawn"] and results["stream_json"]
    print(f"\nGO/NO-GO: {'🟢 GO' if critical else '🔴 NO-GO'}")
    print(f"  pipe_spawn (critical): {'GO' if results['pipe_spawn'] else 'NO-GO'}")
    print(f"  stream_json (critical): {'GO' if results['stream_json'] else 'NO-GO'}")
    print(f"  interactive_pipe (nice-to-have): {'GO' if results['interactive_pipe'] else 'FALLBACK NEEDED'}")
    print(f"  resume (nice-to-have): {'GO' if results['resume'] else 'FALLBACK NEEDED'}")


if __name__ == "__main__":
    asyncio.run(main())
