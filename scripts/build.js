const Path = require('path');
const FileSystem = require('fs');
const { exec } = require('child_process');
const Vite = require('vite');

const PROJECT_ROOT = Path.join(__dirname, '..');
const SRC_ROOT = Path.join(PROJECT_ROOT, 'src');
const BUILD_DIR = Path.join(PROJECT_ROOT, 'build');
const BACKEND_DIR = Path.join(SRC_ROOT, 'backend');
const VENV_DIR = Path.join(BACKEND_DIR, '.venv');

/**
 * 构建前端（Vue + Vite）
 */
function buildFrontend() {
    console.log('[build] Starting frontend build...');
    return Vite.build({
        configFile: Path.join(SRC_ROOT, 'frontend', 'vite.config.js'),
        mode: 'production',
    }).then(() => {
        console.log('[build] Frontend build completed.');
    });
}

/**
 * 构建后端（PyInstaller 打包 FastAPI 服务）
 */
function buildBackend() {
    return new Promise((resolve, reject) => {
        console.log('[build] Starting backend build...');

        // 确定 venv 中 Python 解释器和 pyinstaller 的路径（跨平台）
        const isWindows = process.platform === 'win32';
        const pythonBin = isWindows
            ? Path.join(VENV_DIR, 'Scripts', 'python.exe')
            : Path.join(VENV_DIR, 'bin', 'python');
        const pyinstallerBin = isWindows
            ? Path.join(VENV_DIR, 'Scripts', 'pyinstaller.exe')
            : Path.join(VENV_DIR, 'bin', 'pyinstaller');

        // 检查 Python 解释器是否存在
        if (!FileSystem.existsSync(pythonBin)) {
            const errorMsg = `[build] Python interpreter not found at: ${pythonBin}\n` +
                'Please create a venv: python -m venv .venv';
            console.error(errorMsg);
            reject(new Error(errorMsg));
            return;
        }

        // 检查 pyinstaller 是否存在
        if (!FileSystem.existsSync(pyinstallerBin)) {
            const errorMsg = `[build] PyInstaller not found at: ${pyinstallerBin}\n` +
                'Please install it in the venv: pip install pyinstaller';
            console.error(errorMsg);
            reject(new Error(errorMsg));
            return;
        }

        const distPath = Path.join(BUILD_DIR, 'backend');
        // 使用 entry_point.py 作为 PyInstaller 入口，而非直接使用 src/main.py
        // entry_point.py 会正确设置 sys.path 并以模块方式导入 src.main，
        // 确保 PyInstaller 打包后相对导入（from ..config import ...）能正常工作
        const entryPoint = Path.join(BACKEND_DIR, 'entry_point.py');

        // PyInstaller 包装脚本路径 - 修复 Python 3.12.10 的 dis 模块回归 bug
        // Python 3.12.10 的 dis._get_instructions_bytes 存在 SystemError: Unmatched paren in format
        // 此包装脚本在运行 PyInstaller 前修补 dis.get_instructions 以捕获该错误
        const wrapperScript = Path.join(PROJECT_ROOT, 'scripts', 'pyinstaller_wrapper.py');

        // 项目模块的隐式导入（try/except 导入模式导致 PyInstaller 静态分析无法发现）
        // 由于 src/__init__.py 使 src/ 成为 Python 包，PyInstaller 将模块打包为 src.xxx 命名空间
        // 必须列出所有子模块，因为 try/except 模式下 PyInstaller 无法静态发现这些导入
        const hiddenImports = [
            // src 包及其子包
            'src',
            'src.config', 'src.config.paths', 'src.config.settings',
            'src.database', 'src.database.engine', 'src.database.migration',
            'src.main',
            // 适配器
            'src.adapters', 'src.adapters.ai_provider', 'src.adapters.curseforge', 'src.adapters.modrinth',
            // 数据模型
            'src.models', 'src.models.backup', 'src.models.cache', 'src.models.glossary',
            'src.models.local_modpack', 'src.models.modpack', 'src.models.settings', 'src.models.translation',
            // 解析器
            'src.parsers', 'src.parsers.base_parser', 'src.parsers.bq_parser',
            'src.parsers.ftb_lang_snbt_parser', 'src.parsers.ftb_quest_nbt_parser',
            'src.parsers.jar_parser', 'src.parsers.json_lang_parser', 'src.parsers.kubejs_js_parser',
            'src.parsers.lang_parser', 'src.parsers.parser_registry', 'src.parsers.snbt_parser',
            // 后处理器
            'src.postprocessors', 'src.postprocessors.formatting_checker', 'src.postprocessors.glossary_checker',
            'src.postprocessors.json_validator', 'src.postprocessors.placeholder_checker', 'src.postprocessors.snbt_validator',
            // 路由
            'src.routers', 'src.routers.apply', 'src.routers.feedback', 'src.routers.glossary',
            'src.routers.pack_scan', 'src.routers.search', 'src.routers.settings',
            'src.routers.translate', 'src.routers.workflow',
            // Schema
            'src.schemas', 'src.schemas.apply', 'src.schemas.glossary', 'src.schemas.pack_scan',
            'src.schemas.resourcepack', 'src.schemas.search', 'src.schemas.settings', 'src.schemas.translate',
            // 服务
            'src.services', 'src.services.apply_service', 'src.services.cache_service',
            'src.services.feedback_service', 'src.services.glossary_service', 'src.services.i18n_mod_service',
            'src.services.pack_scanner', 'src.services.resourcepack_service', 'src.services.search_service',
            'src.services.structured_translation_parser', 'src.services.translate_service',
            'src.services.translation_metadata', 'src.services.workflow_service',
            // 工具
            'src.utils', 'src.utils.compact_parser', 'src.utils.ws_manager',
        ];

        // 构建 PyInstaller 命令
        // 使用 Python 解释器运行包装脚本，而非直接调用 pyinstaller.exe
        // 包装脚本会修补 Python 3.12.10 的 dis 模块 bug 后再调用 PyInstaller
        // --path 只需要包含 BACKEND_DIR（src 包的父目录，使 PyInstaller 能正确发现 src 包）
        // 不需要添加 venv 的 site-packages，因为 PyInstaller 已在 venv 环境中运行
        const command = [
            `"${pythonBin}"`,
            `"${wrapperScript}"`,
            '--onefile',
            `--name MCPackLocalizer`,
            `--path "${BACKEND_DIR}"`,
            ...hiddenImports.map(m => `--hidden-import "${m}"`),
            `--distpath "${distPath}"`,
            `--workpath "${Path.join(BACKEND_DIR, 'build')}"`,
            `--specpath "${BACKEND_DIR}"`,
            '--clean',
            '--noconfirm',
            `"${entryPoint}"`,
        ].join(' ');

        console.log(`[build] Running: ${command}`);

        // 在 backend 目录下执行，确保模块导入正确
        exec(command, { cwd: BACKEND_DIR, maxBuffer: 10 * 1024 * 1024 }, (error, stdout, stderr) => {
            if (stdout) console.log(stdout);
            if (stderr) console.error(stderr);
            if (error) {
                console.error('[build] Backend build failed:', error.message);
                reject(error);
            } else {
                console.log('[build] Backend build completed.');
                resolve();
            }
        });
    });
}

// ===== 主流程 =====

// 清理旧的构建输出
if (FileSystem.existsSync(BUILD_DIR)) {
    FileSystem.rmSync(BUILD_DIR, { recursive: true, force: true });
    console.log('[build] Cleaned previous build directory.');
}

// 并行构建前端和后端
Promise.allSettled([
    buildFrontend(),
    buildBackend(),
]).then((results) => {
    const frontendResult = results[0];
    const backendResult = results[1];

    let hasError = false;

    if (frontendResult.status === 'rejected') {
        console.error('[build] Frontend build failed:', frontendResult.reason);
        hasError = true;
    }

    if (backendResult.status === 'rejected') {
        console.error('[build] Backend build failed:', backendResult.reason);
        hasError = true;
    }

    if (hasError) {
        console.error('\n[build] Build completed with errors!');
        process.exit(1);
    } else {
        // 将前端构建产物复制到后端目录下，以便后端 serve 前端静态文件
        const backendFrontendDir = Path.join(BUILD_DIR, 'backend', 'frontend');
        const frontendBuildDir = Path.join(BUILD_DIR, 'frontend');

        if (FileSystem.existsSync(frontendBuildDir)) {
            console.log('[build] Copying frontend build to backend directory...');
            // 如果目标目录已存在则先删除
            if (FileSystem.existsSync(backendFrontendDir)) {
                FileSystem.rmSync(backendFrontendDir, { recursive: true, force: true });
            }
            FileSystem.cpSync(frontendBuildDir, backendFrontendDir, { recursive: true });
            console.log('[build] Frontend files copied to:', backendFrontendDir);
        }

        console.log('\n[build] Frontend & Backend successfully built! (ready for electron-builder)');
    }
});