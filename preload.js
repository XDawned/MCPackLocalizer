const { contextBridge, ipcRenderer } = require('electron')

contextBridge.exposeInMainWorld('electronAPI', {
    minimize: () => ipcRenderer.invoke('window:minimize'),
    maximize: () => ipcRenderer.invoke('window:maximize'),
    close: () => ipcRenderer.invoke('window:close'),
    isMaximized: () => ipcRenderer.invoke('window:isMaximized'),
    onMaximizeChange: (callback) => {
        ipcRenderer.on('window:maximizeChange', (_event, isMaximized) => {
            callback(isMaximized)
        })
    },
    onFocusChange: (callback) => {
        ipcRenderer.on('window:focusChange', (_event, isFocused) => {
            callback(isFocused)
        })
    },
    openDirectoryDialog: () => ipcRenderer.invoke('dialog:openDirectory'),
    closeDirectoryDialog: () => ipcRenderer.invoke('dialog:closeDirectory'),
    // 主题颜色联动：通知主进程更新窗口背景色
    themeChange: (isDark) => ipcRenderer.send('theme:change', isDark)
})
