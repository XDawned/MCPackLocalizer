/**
 * 一键启动开发环境
 *
 * 并行启动以下三个进程：
 *   1. FastAPI 后端（src/backend，端口 25556）
 *   2. Vite 前端开发服务器（src/frontend，端口 5173）
 *   3. Electron 主进程（带 NODE_ENV=development）
 *
 * 使用方法：
 *   node scripts/dev-server.js
 *
 * 任意子进程退出后会自动清理并终止其它进程。
 */

const { spawn } = require('child_process');
const path = require('path');
const http = require('http');
const treeKill = require('tree-kill');

const PROJECT_ROOT = path.join(__dirname, '..');
const FRONTEND_DIR = path.join(PROJECT_ROOT, 'src', 'frontend');
const BACKEND_DIR = path.join(PROJECT_ROOT, 'src', 'backend');

const isWindows = process.platform === 'win32';
const pythonBin = isWindows
    ? path.join(BACKEND_DIR, '.venv', 'Scripts', 'python.exe')
    : path.join(BACKEND_DIR, '.venv', 'bin', 'python');

// 用 npx 调用本地 electron，避免全局依赖问题
const electronBin = isWindows
    ? path.join(PROJECT_ROOT, 'node_modules', '.bin', 'electron.cmd')
    : path.join(PROJECT_ROOT, 'node_modules', '.bin', 'electron');

// 颜色输出
const colors = {
    reset: '\x1b[0m',
    red: '\x1b[31m',
    green: '\x1b[32m',
    yellow: '\x1b[33m',
    blue: '\x1b[34m',
    magenta: '\x1b[35m',
    cyan: '\x1b[36m',
};
const tag = (label, color) => {
    const tagStr = `[${label}]`;
    return `${color}${tagStr.padEnd(12)}${colors.reset}`;
};

const children = [];

function spawnChild(name, command, args, options = {}) {
    const child = spawn(command, args, {
        ...options,
        shell: isWindows,
        env: { ...process.env, ...(options.env || {}) },
    });

    child.stdout.on('data', (data) => {
        const lines = data.toString().split(/\r?\n/).filter(Boolean);
        for (const line of lines) {
            console.log(`${tag(name, colors.cyan)} ${line}`);
        }
    });
    child.stderr.on('data', (data) => {
        const lines = data.toString().split(/\r?\n/).filter(Boolean);
        for (const line of lines) {
            console.log(`${tag(name, colors.yellow)} ${line}`);
        }
    });
    child.on('exit', (code, signal) => {
        console.log(`${tag(name, colors.magenta)} exited (code=${code}, signal=${signal})`);
        cleanup(code);
    });
    child.on('error', (err) => {
        console.error(`${tag(name, colors.red)} error: ${err.message}`);
    });

    children.push({ name, child });
    return child;
}

function cleanup(exitCode = 0) {
    for (const { name, child } of children) {
        if (child.pid && !child.killed) {
            try {
                treeKill(child.pid);
                console.log(`${tag(name, colors.yellow)} killed`);
            } catch (e) {
                // ignore
            }
        }
    }
    // 给子进程一点时间退出
    setTimeout(() => process.exit(exitCode), 500);
}

process.on('SIGINT', () => {
    console.log('\n[dev] Caught SIGINT, shutting down...');
    cleanup(0);
});
process.on('SIGTERM', () => {
    console.log('\n[dev] Caught SIGTERM, shutting down...');
    cleanup(0);
});

/**
 * 轮询后端健康检查端点，直到后端就绪或超时。
 */
function waitForBackend(maxRetries = 60, intervalMs = 1000) {
    return new Promise((resolve) => {
        let retries = 0;
        const check = () => {
            const req = http.get('http://127.0.0.1:25556/health', (res) => {
                if (res.statusCode === 200) {
                    console.log(`${tag('main', colors.green)} backend is ready.`);
                    resolve(true);
                } else {
                    retry();
                }
                res.resume();
            });
            req.on('error', () => retry());
            req.setTimeout(2000, () => {
                req.destroy();
                retry();
            });
        };
        const retry = () => {
            retries++;
            if (retries >= maxRetries) {
                console.error(`${tag('main', colors.red)} backend failed to start within timeout.`);
                resolve(false);
            } else {
                setTimeout(check, intervalMs);
            }
        };
        check();
    });
}

/**
 * 轮询前端 Vite 服务器，直到就绪或超时。
 */
function waitForVite(maxRetries = 60, intervalMs = 1000) {
    return new Promise((resolve) => {
        let retries = 0;
        const check = () => {
            const req = http.get('http://127.0.0.1:5173/', (res) => {
                if (res.statusCode === 200 || res.statusCode === 304) {
                    console.log(`${tag('main', colors.green)} vite is ready.`);
                    resolve(true);
                } else {
                    retry();
                }
                res.resume();
            });
            req.on('error', () => retry());
            req.setTimeout(2000, () => {
                req.destroy();
                retry();
            });
        };
        const retry = () => {
            retries++;
            if (retries >= maxRetries) {
                console.error(`${tag('main', colors.red)} vite failed to start within timeout.`);
                resolve(false);
            } else {
                setTimeout(check, intervalMs);
            }
        };
        check();
    });
}

async function main() {
    console.log(`${tag('main', colors.green)} starting dev environment...`);

    // 1) 启动后端 FastAPI
    console.log(`${tag('main', colors.blue)} starting backend (FastAPI on :25556)...`);
    spawnChild('backend', pythonBin, ['-m', 'src.main'], { cwd: BACKEND_DIR });

    // 2) 启动前端 Vite 开发服务器
    console.log(`${tag('main', colors.blue)} starting frontend (Vite on :5173)...`);
    spawnChild('vite', 'npx', ['vite', '--host', '127.0.0.1', '--port', '5173', '--strictPort'], {
        cwd: FRONTEND_DIR,
    });

    // 3) 等待后端和前端都就绪后再启动 Electron
    const [backendReady, viteReady] = await Promise.all([waitForBackend(), waitForVite()]);
    if (!backendReady || !viteReady) {
        console.error(`${tag('main', colors.red)} prerequisites not ready, aborting.`);
        cleanup(1);
        return;
    }

    console.log(`${tag('main', colors.blue)} starting Electron (development mode)...`);
    spawnChild('electron', electronBin, ['.'], {
        cwd: PROJECT_ROOT,
        env: { NODE_ENV: 'development' },
    });
}

main().catch((err) => {
    console.error(`${tag('main', colors.red)} fatal: ${err.message}`);
    cleanup(1);
});
