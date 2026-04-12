/**
 * Electron Preload Script
 * 
 * 此脚本在渲染进程加载之前运行，用于安全地暴露 Electron API 给渲染进程
 */

const { contextBridge, ipcRenderer } = require('electron');

/**
 * 窗口控制 API
 */
const windowAPI = {
  minimize: () => ipcRenderer.invoke('window:minimize'),
  maximize: () => ipcRenderer.invoke('window:maximize'),
  close: () => ipcRenderer.invoke('window:close'),
};

/**
 * 文件对话框 API
 */
const dialogAPI = {
  openFileDialog: (options) => ipcRenderer.invoke('dialog:openFile', options),
  saveFileDialog: (options) => ipcRenderer.invoke('dialog:saveFile', options),
};

/**
 * 平台信息 API
 */
const platformAPI = {
  get: () => ipcRenderer.invoke('platform:get'),
  value: process.platform,
};

/**
 * 应用信息 API
 */
const appAPI = {
  getVersion: () => ipcRenderer.invoke('app:getVersion'),
};

/**
 * Flask API 配置
 */
const flaskAPI = {
  baseUrl: 'http://127.0.0.1:5000/api',
  port: 5000,
  host: 'http://127.0.0.1',
};

/**
 * 暴露 API 到渲染进程
 */
contextBridge.exposeInMainWorld('electronAPI', {
  // 窗口控制
  window: windowAPI,
  
  // 文件对话框
  dialog: dialogAPI,
  
  // 平台信息
  platform: platformAPI,
  
  // 应用信息
  app: appAPI,
  
  // 版本信息
  versions: {
    node: process.versions.node,
    chrome: process.versions.chrome,
    electron: process.versions.electron,
  },
});

/**
 * 暴露 Flask API 配置
 */
contextBridge.exposeInMainWorld('flaskAPI', flaskAPI);

/**
 * 类型定义（用于 TypeScript 或 IDE 提示）
 * 
 * @typedef {Object} ElectronAPI
 * @property {Object} window - 窗口控制 API
 * @property {Function} window.minimize - 最小化窗口
 * @property {Function} window.maximize - 最大化/还原窗口
 * @property {Function} window.close - 关闭窗口
 * @property {Object} dialog - 文件对话框 API
 * @property {Function} dialog.openFileDialog - 打开文件对话框
 * @property {Function} dialog.saveFileDialog - 保存文件对话框
 * @property {Object} platform - 平台信息 API
 * @property {Function} platform.get - 获取平台信息
 * @property {string} platform.value - 平台值
 * @property {Object} app - 应用信息 API
 * @property {Function} app.getVersion - 获取应用版本
 * @property {Object} versions - 版本信息
 * @property {string} versions.node - Node.js 版本
 * @property {string} versions.chrome - Chrome 版本
 * @property {string} versions.electron - Electron 版本
 */

/**
 * @typedef {Object} FlaskAPI
 * @property {string} baseUrl - Flask API 基础 URL
 * @property {number} port - Flask 端口
 * @property {string} host - Flask 主机地址
 */

/**
 * @global
 * @property {ElectronAPI} electronAPI - Electron API
 * @property {FlaskAPI} flaskAPI - Flask API 配置
 */