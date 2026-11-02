# Photography

Fengcheng Yu 的摄影作品集：https://ffengc.github.io/photography/

## 规矩

- **原图永远不进这个仓库。** 原图放在仓库外面的文件夹里（位置写在 `config.local.yaml`，这个文件不会被提交），脚本只读取，不修改、不复制。
- 仓库里只有处理过的图片：缩略图和大图（长边 2048 像素），都加了水印，GPS 等隐藏信息全部清除，每次生成都会逐张检查。
- `.gitignore` 会挡住 jpg、heic、raw 等原图格式，万一手滑拷进来也不会被提交。

## 网站结构

- **默认页面**：精选第一张作为封面，下面是精选（顺序在 `gallery.yaml` 里定），再往下是其他照片，按时间排。可以切换成"纯按时间"（Chronological），也可以切换大图（两列错落）/ 小图（四列）。
- **作品页面**：原图文件夹里的一个子文件夹就是一组作品（一张或多张）。点任何一张照片都会进入它所在的作品页：一屏一张，显示日期、一句话和相机参数，右下角有张数，键盘方向键可以翻；最后有上一组 / 下一组。再点照片才是全屏大图（大图里不显示参数）。
- **白天 / 黑夜**：默认按访客浏览器的时间自动切换（7:00–19:00 白色），右上角按钮可以手动切换 Auto / Light / Dark。

## 更新照片

1. 原图按作品分文件夹放进原图文件夹。新文件夹会自动变成一组作品，新照片会自动出现。
2. 在 `gallery.yaml` 里调精选顺序、写作品的一句话和每张照片的说明（都可以不写）。
3. 生成网站（需要 `python3 -m pip install pillow pyyaml jinja2`）：
   ```bash
   python3 scripts/build.py
   ```
   只处理新加或改过的照片，最后会检查每张图都没有隐藏信息。
4. 本地预览（只有本机能访问）：
   ```bash
   python3 scripts/serve.py
   ```
   然后打开 http://localhost:8001

## 文件说明

- `gallery.yaml`：网站内容（精选顺序、作品信息、照片说明、水印）
- `scripts/build.py`：处理图片并生成页面；`scripts/serve.py`：本地预览
- `templates/`：页面模板（`home.html` 默认页，`work.html` 作品页）
- `assets/`：样式、脚本、字体 Instrument Serif（OFL 开源协议），以及看大图用的 PhotoSwipe（MIT 协议）
- `index.html`、`w/`、`photos/`：生成的结果，不要手动改

照片版权所有 © Fengcheng Yu，未经授权请勿使用。
