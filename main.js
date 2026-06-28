const path = require('path')
const { app, BrowserWindow, ipcMain, dialog } = require('electron')
const http = require('http')
const fastapiAppUrl = 'http://127.0.0.1:25556'
const treeKill = require('tree-kill');


let fastApiProcess = null

function startFastAPI() {
    console.log('startFastAPI')
    fastApiProcess = require('child_process').spawn(
        path.join(__dirname, '/build/backend/MCPackLocalizer'), { windowsHide: false })
}

/**
 * 轮询后端健康检查端点，直到后端就绪或超时。
 * @param {number} maxRetries 最大重试次数
 * @param {number} intervalMs 每次重试间隔（毫秒）
 * @returns {Promise<boolean>} 后端是否就绪
 */
function waitForBackend(maxRetries = 60, intervalMs = 1000) {
    return new Promise((resolve) => {
        let retries = 0
        const check = () => {
            const req = http.get('http://127.0.0.1:25556/health', (res) => {
                if (res.statusCode === 200) {
                    console.log('[main] Backend is ready.')
                    resolve(true)
                } else {
                    retry()
                }
                res.resume() // 丢弃响应体
            })
            req.on('error', () => {
                retry()
            })
            req.setTimeout(2000, () => {
                req.destroy()
                retry()
            })
        }
        const retry = () => {
            retries++
            if (retries >= maxRetries) {
                console.error('[main] Backend failed to start within timeout.')
                resolve(false)
            } else {
                setTimeout(check, intervalMs)
            }
        }
        check()
    })
}

const createWindow = () => {
    const win = new BrowserWindow({
        width: 1280,
        height: 800,
        minWidth: 900,
        minHeight: 600,
        icon: path.join(__dirname, 'icon.ico'),
        backgroundColor: '#0f172a',
        frame: false,
        show: false,
        webPreferences: {
            contextIsolation: true,
            nodeIntegration: false,
            preload: path.join(__dirname, 'preload.js')
        }
    })

    win.on('ready-to-show', () => {
        win.show()
    })

    win.on('maximize', () => {
        win.webContents.send('window:maximizeChange', true)
    })

    win.on('unmaximize', () => {
        win.webContents.send('window:maximizeChange', false)
    })

    win.on('focus', () => {
        win.webContents.send('window:focusChange', true)
    })

    win.on('blur', () => {
        win.webContents.send('window:focusChange', false)
    })

    if(process.env.NODE_ENV === 'development') {
        win.loadURL('http://localhost:5173');
        win.webContents.openDevTools();
    } else {
        console.log(__dirname)
        // 先启动后端，等待就绪后通过后端 serve 的前端页面加载（同源，避免 CORS 问题）
        startFastAPI()
        waitForBackend().then((ready) => {
            if (ready) {
                win.loadURL('http://127.0.0.1:25556')
            } else {
                console.error('[main] Backend not ready, loading frontend from file...')
                win.loadFile(path.join(__dirname, '/build/frontend/index.html'))
            }
        })
    }

    return win
}

const stopFastAPI = () => {
    if (fastApiProcess !== null) {
        treeKill(fastApiProcess.pid)
        fastApiProcess = null
    }
}

// IPC handlers for custom title bar
ipcMain.handle('window:minimize', (event) => {
    BrowserWindow.fromWebContents(event.sender).minimize()
})

ipcMain.handle('window:maximize', (event) => {
    const win = BrowserWindow.fromWebContents(event.sender)
    if (win.isMaximized()) {
        win.unmaximize()
    } else {
        win.maximize()
    }
})

ipcMain.handle('window:close', (event) => {
    BrowserWindow.fromWebContents(event.sender).close()
})

ipcMain.handle('window:isMaximized', (event) => {
    return BrowserWindow.fromWebContents(event.sender).isMaximized()
})

ipcMain.handle('dialog:openDirectory', async (event) => {
    const win = BrowserWindow.fromWebContents(event.sender)
    console.log('[dialog:openDirectory] invoked', {
        browserWindowFound: !!win,
        isDestroyed: win?.isDestroyed?.() ?? null,
        env: process.env.NODE_ENV || 'production'
    })

    const result = await dialog.showOpenDialog(win, {
        properties: ['openDirectory']
    })

    console.log('[dialog:openDirectory] result', {
        canceled: result.canceled,
        filePathsCount: result.filePaths.length,
        firstPath: result.filePaths[0] || null
    })

    if (result.canceled || !result.filePaths.length) {
        return null
    }
    return result.filePaths[0]
})

ipcMain.handle('dialog:closeDirectory', async (event) => {
    const win = BrowserWindow.fromWebContents(event.sender)
    console.log('[dialog:closeDirectory] invoked', {
        browserWindowFound: !!win,
        isDestroyed: win?.isDestroyed?.() ?? null
    })
    return true
})

// 主题颜色联动：渲染进程通知主进程更新窗口背景色
ipcMain.on('theme:change', (event, isDark) => {
    const win = BrowserWindow.fromWebContents(event.sender)
    if (win && !win.isDestroyed()) {
        win.setBackgroundColor(isDark ? '#0f172a' : '#f5f7fb')
    }
})

app.on('before-quit', stopFastAPI)

app.whenReady().then(() => {
    createWindow()
     app.on('activate', () => {
        if (BrowserWindow.getAllWindows().length === 0) createWindow()
    })
    
})

app.on('window-all-closed', () => {
    console.log(process.platform)
    // for not macOS
    if (process.platform !== 'darwin') {
        app.quit()
    }
})
