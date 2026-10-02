"""HTTP media 领域适配；服务引用来自 OMRSHandler.services，保持统一边界。"""

class MediaRoutes:

    def _entry_background_post(self):
        """分块接收入口背景，文件落盘后才在写锁内提交配置。"""
        raw_path = None
        upload_path = None
        try:
            length = int(self.headers.get('Content-Length', 0))
            max_request = self.services.entry_background.MAX_UPLOAD_BYTES + 1024 * 1024
            if length <= 0 or length > max_request:
                raise ValueError('入口背景请求不能超过 200 MB')
            content_type = self.headers.get('Content-Type', '')
            if 'multipart/form-data' not in content_type:
                raise ValueError('请用 multipart/form-data 上传入口背景')
            fields, file_info, raw_path = self._read_entry_background_multipart(length, content_type)
            upload = None
            if file_info:
                filename, declared_mime, upload_path = file_info
                upload = self.services.entry_background.inspect_upload(upload_path, filename, declared_mime)
                upload['path'] = upload_path
            mode = fields.get('mode', self.services.entry_background.DEFAULT_MODE)
            style = fields.get('style', self.services.entry_background.DEFAULT_STYLE)
            blur = fields.get('blur_px', self.services.entry_background.DEFAULT_BLUR_PX)
            asset_id = fields.get('asset_id', '')
            with self.services.locking.write_lock():
                state = self.services.entry_background.save_state(self.vault_path, mode, style, blur, asset_id=asset_id, upload=upload)
            upload_path = None
            self._json({'status': 'ok', 'entry_background': state})
        except (ValueError, TypeError, OSError) as exc:
            self._error(exc)
        finally:
            for path in (raw_path, upload_path):
                if path:
                    try:
                        self.services.os.remove(path)
                    except OSError:
                        pass

    def _read_entry_background_multipart(self, length, content_type):
        """把 multipart 请求先流式写入临时文件，再用 mmap 分离字段和文件。

        这样 200MB 视频不会同时驻留在 Python 堆内存中；请求只允许一个 file 字段。
        """
        marker_text = 'boundary='
        if marker_text not in content_type:
            raise ValueError('缺少 multipart boundary')
        boundary = content_type.split(marker_text, 1)[1].strip().strip('"').split(';', 1)[0]
        if not boundary or len(boundary) > 200:
            raise ValueError('multipart boundary 不合法')
        upload_dir = self.services.entry_background.background_dir(self.vault_path)
        fd, raw_path = self.services.tempfile.mkstemp(prefix='.request-', suffix='.multipart', dir=upload_dir)
        try:
            with self.services.os.fdopen(fd, 'wb') as raw:
                remaining = length
                while remaining:
                    chunk = self.rfile.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ValueError('上传请求提前结束')
                    raw.write(chunk)
                    remaining -= len(chunk)
                raw.flush()
                self.services.os.fsync(raw.fileno())
            fields = {}
            file_info = None
            boundary_bytes = b'--' + boundary.encode('ascii', errors='strict')
            with open(raw_path, 'rb') as raw, self.services.mmap.mmap(raw.fileno(), 0, access=self.services.mmap.ACCESS_READ) as mapped:
                marker = mapped.find(boundary_bytes)
                if marker < 0:
                    raise ValueError('multipart 请求缺少边界')
                while marker >= 0:
                    after = marker + len(boundary_bytes)
                    if mapped[after:after + 2] == b'--':
                        break
                    if mapped[after:after + 2] != b'\r\n':
                        raise ValueError('multipart 边界格式错误')
                    part_start = after + 2
                    next_marker = mapped.find(boundary_bytes, part_start)
                    if next_marker < 0:
                        raise ValueError('multipart 请求不完整')
                    part_end = next_marker - 2 if mapped[next_marker - 2:next_marker] == b'\r\n' else next_marker
                    header_end = mapped.find(b'\r\n\r\n', part_start, part_end)
                    if header_end < 0:
                        raise ValueError('multipart 字段缺少头部')
                    header_text = bytes(mapped[part_start:header_end]).decode('utf-8', errors='replace')
                    headers = {}
                    for line in header_text.split('\r\n'):
                        if ':' in line:
                            key, value = line.split(':', 1)
                            headers[key.strip().lower()] = value.strip()
                    disposition = headers.get('content-disposition', '')
                    name_match = self.services.re.search('name="([^"]+)"', disposition)
                    if not name_match:
                        raise ValueError('multipart 字段缺少 name')
                    name = name_match.group(1)
                    body_start = header_end + 4
                    body_size = max(0, part_end - body_start)
                    filename_match = self.services.re.search('filename="([^"]*)"', disposition)
                    if filename_match:
                        if file_info is not None:
                            raise ValueError('一次只能上传一个入口背景文件')
                        filename = self.services.os.path.basename(filename_match.group(1)) or 'background'
                        fd, path = self.services.tempfile.mkstemp(prefix='.media-', suffix='.upload', dir=upload_dir)
                        with self.services.os.fdopen(fd, 'wb') as target:
                            offset = body_start
                            while offset < part_end:
                                block = mapped[offset:min(offset + 1024 * 1024, part_end)]
                                target.write(block)
                                offset += len(block)
                            target.flush()
                            self.services.os.fsync(target.fileno())
                        file_info = (filename, headers.get('content-type', ''), path)
                    else:
                        if body_size > 64 * 1024:
                            raise ValueError('入口背景字段过大')
                        fields[name] = bytes(mapped[body_start:part_end]).decode('utf-8', errors='strict')
                    marker = next_marker
            return (fields, file_info, raw_path)
        except Exception:
            try:
                self.services.os.remove(raw_path)
            except OSError:
                pass
            raise

    def _multipart_files(self, body, content_type):
        """解析 multipart 里的全部文件 → [(filename, bytes)]。"""
        marker = 'boundary='
        if marker not in content_type:
            raise ValueError('缺少 multipart boundary')
        boundary = content_type.split(marker, 1)[1].strip().strip('"').split(';')[0]
        delimiter = ('--' + boundary).encode('utf-8')
        files = []
        for part in body.split(delimiter):
            if b'Content-Disposition' not in part or b'\r\n\r\n' not in part:
                continue
            headers, payload = part.split(b'\r\n\r\n', 1)
            if payload.endswith(b'\r\n'):
                payload = payload[:-2]
            header_text = headers.decode('utf-8', errors='ignore')
            if 'filename=' not in header_text:
                continue
            filename = 'image'
            header_text = next((line for line in header_text.split('\r\n') if 'Content-Disposition' in line), header_text)
            for item in header_text.split(';'):
                item = item.strip()
                if item.startswith('filename='):
                    filename = item.split('=', 1)[1].strip().strip('"') or filename
                    break
            files.append((self.services.os.path.basename(filename), payload))
        return files

    def _uploads_post(self, path):
        try:
            if path == '/api/uploads/chunk':
                params = dict(self.services.urllib.parse.parse_qsl(self.services.urllib.parse.urlparse(self.path).query))
                result = self.services.uploads.chunk(self.vault_path, params.get('upload_id', ''), int(params.get('index', '-1')), self.rfile.read(self.services.http_io.CHUNK_BYTES + 1))
            else:
                data = self.services.http_io.json_body(self)
                if path == '/api/uploads/start':
                    result = self.services.uploads.start(self.vault_path, data.get('filename', 'image'), data.get('mime', ''), data.get('total_bytes'), data.get('purpose', 'image'))
                elif path == '/api/uploads/complete':
                    result = self.services.uploads.complete(self.vault_path, data.get('upload_id', ''), data.get('sha256'))
                else:
                    self._json({'status': 'error', 'msg': '接口不存在'}, 404)
                    return
            self._json({'status': 'ok', **result})
        except Exception as exc:
            self._error(exc)

    def _handle_backup_import(self):
        temporary = None
        try:
            if hasattr(self, '_prepared_files'):
                if len(self._prepared_files) != 1:
                    raise ValueError('一次只允许上传一个备份文件')
                filename, reference = self._prepared_files[0]
                temporary = self.services.tempfile.NamedTemporaryFile('w+b')
                self.services.uploads.copy_to(self.vault_path, reference, temporary, purpose='backup')
                temporary.flush()
                payload = temporary.name
            elif hasattr(self, '_prepared_json'):
                reference = self.services.http_io.json_body(self)
                uploaded = self.services.uploads.resolve(self.vault_path, reference, purpose='backup')
                filename = uploaded['filename']
                temporary = self.services.tempfile.NamedTemporaryFile('w+b')
                self.services.uploads.copy_to(self.vault_path, reference, temporary, purpose='backup')
                temporary.flush()
                payload = temporary.name
            else:
                filename = self.headers.get('X-Filename', 'backup.zip')
                temporary = self.services.tempfile.NamedTemporaryFile('w+b')
                self.services.shutil.copyfileobj(self.rfile, temporary, 65536)
                temporary.flush()
                payload = temporary.name
            self._json(self.services.prepare_backup_import(self.vault_path, payload, filename))
        except Exception as exc:
            self._error(exc)
        finally:
            if temporary:
                temporary.close()

    def _multipart_file(self, body, content_type):
        if 'multipart/form-data' not in content_type:
            filename = self.headers.get('X-Filename', 'backup.zip')
            return (filename, body)
        marker = 'boundary='
        if marker not in content_type:
            raise ValueError('缺少 multipart boundary')
        boundary = content_type.split(marker, 1)[1].strip().strip('"')
        delimiter = ('--' + boundary).encode('utf-8')
        for part in body.split(delimiter):
            if b'Content-Disposition' not in part or b'\r\n\r\n' not in part:
                continue
            headers, payload = part.split(b'\r\n\r\n', 1)
            if payload.endswith(b'\r\n'):
                payload = payload[:-2]
            header_text = headers.decode('utf-8', errors='ignore')
            if 'filename=' not in header_text:
                continue
            filename = 'backup.zip'
            for item in header_text.split(';'):
                item = item.strip()
                if item.startswith('filename='):
                    filename = item.split('=', 1)[1].strip().strip('"') or filename
                    break
            return (self.services.os.path.basename(filename), payload)
        raise ValueError('未找到上传的备份文件')
