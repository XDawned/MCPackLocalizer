const { app, BrowserWindow, ipcMain, dialog } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const axios = require('axios');

let mainWindow;
let flaskProcess;
const FLASK_PORT = 5000;
const FLASK_HOST = 'http://127.0.0.1';

/**
 * 启动 Flask 服务
 * @returns {Promise<void>}
 */
function startFlaskServer() {
  return new Promise((resolve, reject) => {
    const isDev = process.env.NODE_ENV !== 'production';
    
    // 确定后端路径和 Python 路径
    const backendPath = isDev 
      ? path.join(__dirname, '../backend')
      : path.join(process.resourcesPath, 'backend');
    
    const pythonPath = isDev
      ? 'python'
      : path.join(process.resourcesPath, 'venv', 'Scripts', 'python.exe');

    console.log('Starting Flask server...');
    console.log('Backend path:', backendPath);
    console.log('Python path:', pythonPath);

    // 启动 Flask 进程
    flaskProcess = spawn(pythonPath, [path.join(backendPath, 'app.py')], {
      env: { 
        ...process.env,
        FLASK_PORT: FLASK_PORT,
        FLASK_ENV: isDev ? 'development' : 'production'
      }
    });

    // 处理 Flask 输出
    flaskProcess.stdout.on('data', (data) => {
      const output = data.toString();
      console.log(`Flask: ${output}`);
      if (output.includes('Running on') || output.includes('Running on http')) {
        resolve();
      }
    });

    flaskProcess.stderr.on('data', (data) => {
      console.error(`Flask Error: ${data.toString()}`);
    });

    flaskProcess.on('close', (code) => {
      console.log(`Flask process exited with code ${code}`);
    });

    flaskProcess.on('error', (err) => {
      console.error('Failed to start Flask:', err);
      reject(err);
    });

    // 超时处理
    setTimeout(() => {
      reject(new Error('Flask server startup timeout'));
    }, 10000);
  });
}

/**
 * 等待 Flask 服务就绪
 * @returns {Promise<boolean>}
 */
async function waitForFlaskServer() {
  const maxAttempts = 20;
  for (let i = 0; i < maxAttempts; i++) {
    try {
      await axios.get(`${FLASK_HOST}:${FLASK_PORT}/api/health`);
      console.log('Flask server is ready');
      return true;
    } catch (e) {
      console.log(`Waiting for Flask server... attempt ${i + 1}`);
      await new Promise(r => setTimeout(r, 500));
    }
  }
  throw new Error('Flask server failed to start');
}

/**
 * 创建主窗口
 */
function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 800,
    minWidth: 800,
    minHeight: 600,
    frame: false, // 无边框窗口
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
    icon: path.join(__dirname, '../public/icon.ico'),
    show: false,
    backgroundColor: '#1b1b1b',
  });

  // 加载页面
  if (process.env.NODE_ENV === 'development') {
    mainWindow.loadURL('http://localhost:5173');
    mainWindow.webContents.openDevTools();
  } else {
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'));
  }

  // 窗口准备好后显示
  mainWindow.once('ready-to-show', () => {
    mainWindow.show();
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

/**
 * 注册 IPC 处理器
 */
function registerIPCHandlers() {
  // 窗口控制
  ipcMain.handle('window:minimize', () => {
    if (mainWindow) {
      mainWindow.minimize();
    }
  });

  ipcMain.handle('window:maximize', () => {
    if (mainWindow) {
      if (mainWindow.isMaximized()) {
        mainWindow.unmaximize();
      } else {
        mainWindow.maximize();
      }
    }
  });

  ipcMain.handle('window:close', () => {
    if (mainWindow) {
      mainWindow.close();
    }
  });

  // 文件对话框
  ipcMain.handle('dialog:openFile', async (event, options) => {
    if (!mainWindow) return { canceled: true };
    const result = await dialog.showOpenDialog(mainWindow, options);
    return result;
  });

  ipcMain.handle('dialog:saveFile', async (event, options) => {
    if (!mainWindow) return { canceled: true };
    const result = await dialog.showSaveDialog(mainWindow, options);
    return result;
  });

  // 获取平台信息
  ipcMain.handle('platform:get', () => {
    return process.platform;
  });

  // 获取应用版本
  ipcMain.handle('app:getVersion', () => {
    return app.getVersion();
  });
}

// 应用生命周期管理
app.whenReady().then(async () => {
  console.log('Application starting...');
  
  try {
    // 注册 IPC 处理器
    registerIPCHandlers();
    
    // 启动 Flask 服务
    console.log('Starting Flask server...');
    await startFlaskServer();
    
    // 等待 Flask 服务就绪
    console.log('Waiting for Flask server to be ready...');
    await waitForFlaskServer();
    
    // 创建主窗口
    console.log('Creating main window...');
    createWindow();
    
    console.log('Application started successfully');
  } catch (error) {
    console.error('Failed to start application:', error);
    
    // 显示错误对话框
    dialog.showErrorBox(
      '启动失败',
      `应用程序启动失败：${error.message}\n\n请检查 Python 环境是否正确安装。`
    );
    
    app.quit();
  }
});

app.on('window-all-closed', () => {
  console.log('All windows closed, cleaning up...');
  
  // 清理 Flask 进程
  if (flaskProcess) {
    console.log('Killing Flask process...');
    flaskProcess.kill();
    flaskProcess = null;
  }
  
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});

app.on('before-quit', () => {
  console.log('Application quitting, cleaning up...');
  
  // 清理 Flask 进程
  if (flaskProcess) {
    console.log('Killing Flask process...');
    flaskProcess.kill();
    flaskProcess = null;
  }
});

// 处理未捕获的异常
process.on('uncaughtException', (error) => {
  console.error('Uncaught exception:', error);
});

process.on('unhandledRejection', (reason, promise) => {
  console.error('Unhandled rejection at:', promise, 'reason:', reason);
});