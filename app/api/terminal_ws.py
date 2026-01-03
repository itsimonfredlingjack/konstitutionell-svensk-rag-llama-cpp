"""
WebSocket endpoint för riktig terminal med PTY
Spawnar en bash-session och streamar I/O via WebSocket
"""
import asyncio
import pty
import os
import struct
import fcntl
import termios
import json
import signal
from typing import Optional
from fastapi import WebSocket, WebSocketDisconnect


async def terminal_websocket(websocket: WebSocket):
    """WebSocket endpoint för interaktiv terminal"""
    await websocket.accept()

    master_fd: Optional[int] = None
    pid: Optional[int] = None
    read_task: Optional[asyncio.Task] = None

    try:
        # Create PTY
        master_fd, slave_fd = pty.openpty()

        # Set non-blocking
        flags = fcntl.fcntl(master_fd, fcntl.F_GETFL)
        fcntl.fcntl(master_fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)

        # Spawn bash
        pid = os.fork()
        if pid == 0:
            # Child process
            os.close(master_fd)
            os.setsid()
            os.dup2(slave_fd, 0)
            os.dup2(slave_fd, 1)
            os.dup2(slave_fd, 2)
            if slave_fd > 2:
                os.close(slave_fd)

            # Set environment
            env = os.environ.copy()
            env['TERM'] = 'xterm-256color'
            env['COLORTERM'] = 'truecolor'

            # Execute bash
            os.execvpe('/bin/bash', ['/bin/bash', '--login'], env)

        # Parent process
        os.close(slave_fd)

        async def read_pty():
            """Read PTY output and send to WebSocket"""
            loop = asyncio.get_event_loop()
            while True:
                try:
                    # Use run_in_executor for non-blocking read
                    data = await asyncio.wait_for(
                        loop.run_in_executor(
                            None,
                            lambda: os.read(master_fd, 4096)
                        ),
                        timeout=0.1
                    )
                    if data:
                        await websocket.send_text(
                            data.decode('utf-8', errors='replace')
                        )
                except asyncio.TimeoutError:
                    # No data available, continue
                    await asyncio.sleep(0.01)
                except OSError:
                    # PTY closed
                    break
                except Exception as e:
                    print(f"[Terminal] Read error: {e}")
                    break

        read_task = asyncio.create_task(read_pty())

        # Handle incoming messages
        try:
            while True:
                data = await websocket.receive_text()
                message = json.loads(data)

                if message.get('type') == 'input':
                    input_data = message.get('data', '')
                    os.write(master_fd, input_data.encode())

                elif message.get('type') == 'resize':
                    cols = message.get('cols', 80)
                    rows = message.get('rows', 24)
                    winsize = struct.pack('HHHH', rows, cols, 0, 0)
                    fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)

        except WebSocketDisconnect:
            print("[Terminal] Client disconnected")

    except Exception as e:
        print(f"[Terminal] Error: {e}")

    finally:
        # Cleanup
        if read_task:
            read_task.cancel()
            try:
                await read_task
            except asyncio.CancelledError:
                pass

        if master_fd is not None:
            try:
                os.close(master_fd)
            except OSError:
                pass

        if pid is not None and pid > 0:
            try:
                os.kill(pid, signal.SIGTERM)
                # Give it a moment to terminate
                await asyncio.sleep(0.1)
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass
                os.waitpid(pid, os.WNOHANG)
            except OSError:
                pass

        print("[Terminal] Session closed")
