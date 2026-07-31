package main

import (
	"bufio"
	"bytes"
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/base64"
	"encoding/binary"
	"encoding/hex"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"io/fs"
	"net"
	"net/http"
	"net/url"
	"os"
	"os/signal"
	"path"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
	"sync"
	"syscall"
	"time"

	"github.com/pkg/sftp"
	"golang.org/x/crypto/ssh"
)

const (
	userAgent        = "LanotaChinaTokenUploader/1.2"
	chinaPackageName = "com.gmzon.taptap.lanota"
	androidUserRoot  = "/data/user"
	portalHost       = "lanota.gmzon.com"
	tokenStorageKey  = "lanota.portal.chinaToken"
	userStorageKey   = "lanota.portal.chinaUser"
	defaultWatchTime = 10 * time.Minute
	devToolsPollTime = 250 * time.Millisecond
	devToolsEvalTime = 500 * time.Millisecond
)

var storagePackageNames = []string{
	chinaPackageName,
	"com.android.chrome",
	"com.microsoft.emmx",
}

var jwtPattern = regexp.MustCompile(`eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}`)
var devToolsSocketPattern = regexp.MustCompile(`@?([A-Za-z0-9_.:-]*devtools_remote[A-Za-z0-9_.:-]*)\s*$`)

type config struct {
	ServerHost          string
	ServerPort          int
	ServerUser          string
	ServerPassword      string
	ServerHostKeySHA256 string
	RemotePath          string
	PortalMeURL         string
	ScanInterval        time.Duration
	ReconcileInterval   time.Duration
	RetryMin            time.Duration
	RetryMax            time.Duration
	MaxFileBytes        int64
	ConnectTimeout      time.Duration
	WatchTimeout        time.Duration
	StateFile           string
	ConfigDirectory     string
}

type jwtHeader struct {
	Algorithm string `json:"alg"`
}

type jwtPayload struct {
	Issuer    string `json:"iss"`
	Subject   string `json:"sub"`
	IssuedAt  int64  `json:"iat"`
	ExpiresAt int64  `json:"exp"`
}

type candidate struct {
	Token   string
	Payload jwtPayload
	Source  string
}

type daemonState struct {
	UploadedTokenSHA256 string `json:"uploaded_token_sha256,omitempty"`
	UploadedExpiresAt   int64  `json:"uploaded_expires_at,omitempty"`
	PendingToken        string `json:"pending_token,omitempty"`
	PendingSubject      string `json:"pending_subject,omitempty"`
	PendingExpiresAt    int64  `json:"pending_expires_at,omitempty"`
	PendingSource       string `json:"pending_source,omitempty"`
	LastScanAt          int64  `json:"last_scan_at,omitempty"`
	LastSuccessAt       int64  `json:"last_success_at,omitempty"`
	LastErrorAt         int64  `json:"last_error_at,omitempty"`
	LastError           string `json:"last_error,omitempty"`
}

type authFile struct {
	ChinaToken string `json:"china_token"`
	UID        string `json:"uid"`
	ExpiresAt  int64  `json:"expires_at"`
	SavedAt    int64  `json:"saved_at"`
}

type daemon struct {
	config             config
	state              daemonState
	rejected           map[string]int64
	nextAttempt        time.Time
	retryDelay         time.Duration
	lastNoToken        time.Time
	storageFiles       []string
	lastStorageRefresh time.Time
	cleanupRemote      bool
}

type devToolsTarget struct {
	ID                   string `json:"id"`
	Type                 string `json:"type"`
	URL                  string `json:"url"`
	WebSocketDebuggerURL string `json:"webSocketDebuggerUrl"`
}

type devToolsMessage struct {
	ID     int64           `json:"id,omitempty"`
	Method string          `json:"method,omitempty"`
	Result json.RawMessage `json:"result,omitempty"`
	Params json.RawMessage `json:"params,omitempty"`
}

type networkRequestEvent struct {
	Request struct {
		URL      string         `json:"url"`
		Headers  map[string]any `json:"headers"`
		PostData string         `json:"postData"`
	} `json:"request"`
}

type webSocketConnection struct {
	conn         net.Conn
	reader       *bufio.Reader
	targetURL    string
	lastEvaluate time.Time
	writeMu      sync.Mutex
	nextID       int64
}

func main() {
	configPath := flag.String("config", "config.conf", "configuration file")
	command := flag.String("command", "daemon", "daemon, scan, upload, status, or clear")
	stateFile := flag.String("state-file", "", "override state file (diagnostic helper)")
	once := flag.Bool("once", false, "scan once and exit")
	scanFile := flag.String("scan-file", "", "scan only this file (test helper)")
	dryRun := flag.Bool("dry-run", false, "verify without uploading")
	remotePath := flag.String("remote-path", "", "override remote path (diagnostic helper)")
	cleanupRemote := flag.Bool("cleanup-remote", false, "delete diagnostic remote file after verification")
	flag.Parse()

	cfg, err := loadConfig(*configPath)
	if err != nil {
		fatalf("configuration error: %v", err)
	}
	if *remotePath != "" {
		cfg.RemotePath = *remotePath
	}
	if *stateFile != "" {
		cfg.StateFile = *stateFile
	}
	if *cleanupRemote && *remotePath == "" {
		fatalf("-cleanup-remote requires an explicit diagnostic -remote-path")
	}
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()
	d := &daemon{
		config:        cfg,
		state:         readState(cfg.StateFile),
		rejected:      make(map[string]int64),
		retryDelay:    cfg.RetryMin,
		cleanupRemote: *cleanupRemote,
	}
	if *command != "daemon" {
		switch *command {
		case "scan":
			if *scanFile != "" {
				err = d.scanAndStage(ctx, *scanFile)
			} else {
				err = d.watchAndStage(ctx)
			}
			if err != nil {
				fatalf("scan failed: %v", err)
			}
		case "upload":
			if err = d.uploadPending(ctx); err != nil {
				fatalf("upload failed: %v", err)
			}
		case "status":
			printStatus(d.state)
		case "clear":
			d.state.PendingToken = ""
			d.state.PendingSubject = ""
			d.state.PendingExpiresAt = 0
			d.state.PendingSource = ""
			if err = writeState(cfg.StateFile, d.state); err != nil {
				fatalf("clear failed: %v", err)
			}
			printStatus(d.state)
		default:
			fatalf("unknown command: %s", *command)
		}
		return
	}

	logf("daemon started; scan interval=%s", cfg.ScanInterval)

	if *once {
		found, runErr := d.runOnce(ctx, *scanFile, *dryRun)
		if runErr != nil {
			fatalf("scan failed: %v", runErr)
		}
		if !found {
			fatalf("no valid Lanota China token found")
		}
		return
	}

	ticker := time.NewTicker(cfg.ScanInterval)
	defer ticker.Stop()
	for {
		_, runErr := d.runOnce(ctx, "", *dryRun)
		if runErr != nil {
			logf("scan/upload error: %v", runErr)
		}
		select {
		case <-ctx.Done():
			logf("daemon stopped")
			return
		case <-ticker.C:
		}
	}
}

func loadConfig(fileName string) (config, error) {
	absPath, err := filepath.Abs(fileName)
	if err != nil {
		return config{}, err
	}
	raw, err := os.ReadFile(absPath)
	if err != nil {
		return config{}, err
	}
	values := make(map[string]string)
	for index, line := range strings.Split(string(raw), "\n") {
		line = strings.TrimSpace(strings.TrimSuffix(line, "\r"))
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		key, value, found := strings.Cut(line, "=")
		if !found {
			return config{}, fmt.Errorf("line %d has no '='", index+1)
		}
		values[strings.TrimSpace(key)] = strings.TrimSpace(value)
	}

	integer := func(key string, fallback int64) (int64, error) {
		value := values[key]
		if value == "" {
			return fallback, nil
		}
		parsed, parseErr := strconv.ParseInt(value, 10, 64)
		if parseErr != nil || parsed <= 0 {
			return 0, fmt.Errorf("%s must be a positive integer", key)
		}
		return parsed, nil
	}

	port, err := integer("server_port", 22)
	if err != nil {
		return config{}, err
	}
	scanSeconds, err := integer("scan_interval_seconds", 15)
	if err != nil {
		return config{}, err
	}
	reconcileSeconds, err := integer("reconcile_interval_seconds", 3600)
	if err != nil {
		return config{}, err
	}
	retryMinSeconds, err := integer("retry_min_seconds", 30)
	if err != nil {
		return config{}, err
	}
	retryMaxSeconds, err := integer("retry_max_seconds", 1800)
	if err != nil {
		return config{}, err
	}
	maxFileBytes, err := integer("max_file_bytes", 64*1024*1024)
	if err != nil {
		return config{}, err
	}
	connectSeconds, err := integer("connect_timeout_seconds", 20)
	if err != nil {
		return config{}, err
	}
	watchSeconds, err := integer("watch_timeout_seconds", int64(defaultWatchTime/time.Second))
	if err != nil {
		return config{}, err
	}

	directory := filepath.Dir(absPath)
	stateFile := values["state_file"]
	if stateFile == "" {
		stateFile = "state/state.json"
	}
	if !filepath.IsAbs(stateFile) {
		stateFile = filepath.Join(directory, filepath.FromSlash(stateFile))
	}

	result := config{
		ServerHost:          values["server_host"],
		ServerPort:          int(port),
		ServerUser:          values["server_user"],
		ServerPassword:      values["server_password"],
		ServerHostKeySHA256: values["server_host_key_sha256"],
		RemotePath:          values["remote_path"],
		PortalMeURL:         values["portal_me_url"],
		ScanInterval:        time.Duration(scanSeconds) * time.Second,
		ReconcileInterval:   time.Duration(reconcileSeconds) * time.Second,
		RetryMin:            time.Duration(retryMinSeconds) * time.Second,
		RetryMax:            time.Duration(retryMaxSeconds) * time.Second,
		MaxFileBytes:        maxFileBytes,
		ConnectTimeout:      time.Duration(connectSeconds) * time.Second,
		WatchTimeout:        time.Duration(watchSeconds) * time.Second,
		StateFile:           stateFile,
		ConfigDirectory:     directory,
	}
	if result.PortalMeURL == "" {
		result.PortalMeURL = "https://lanota.gmzon.com/portal/api/me"
	}
	if result.ServerHost == "" || result.ServerUser == "" || result.ServerPassword == "" ||
		result.ServerPassword == "CHANGE_ME" || result.RemotePath == "" {
		return config{}, errors.New("server host, user, password and remote path are required")
	}
	if !strings.HasPrefix(result.ServerHostKeySHA256, "SHA256:") {
		return config{}, errors.New("server_host_key_sha256 must use SHA256:... format")
	}
	if result.RetryMax < result.RetryMin {
		return config{}, errors.New("retry_max_seconds must be >= retry_min_seconds")
	}
	return result, nil
}

func (d *daemon) runOnce(ctx context.Context, scanFile string, dryRun bool) (bool, error) {
	now := time.Now()
	d.state.LastScanAt = now.Unix()
	files := []string{scanFile}
	if scanFile == "" {
		if d.lastStorageRefresh.IsZero() || now.Sub(d.lastStorageRefresh) >= time.Minute {
			d.storageFiles = discoverPackageStorageFiles(androidUserRoot, chinaPackageName)
			d.lastStorageRefresh = now
		}
		files = d.storageFiles
	}
	candidates, err := scanCandidateFiles(d.config, files)
	if err != nil {
		d.recordError(err)
		return false, err
	}
	if len(candidates) == 0 {
		_ = writeState(d.config.StateFile, d.state)
		if d.lastNoToken.IsZero() || now.Sub(d.lastNoToken) >= time.Hour {
			logf("no unexpired Lanota China token found")
			d.lastNoToken = now
		}
		return false, nil
	}

	selected := candidates[0]
	tokenHash := tokenSHA256(selected.Token)
	if rejectedUntil := d.rejected[tokenHash]; rejectedUntil > now.Unix() {
		return true, nil
	}
	if now.Before(d.nextAttempt) {
		return true, nil
	}
	if d.state.UploadedTokenSHA256 == tokenHash &&
		now.Sub(time.Unix(d.state.LastSuccessAt, 0)) < d.config.ReconcileInterval {
		return true, nil
	}

	if err = verifyPortalToken(ctx, d.config, selected.Token); err != nil {
		var rejectedError portalRejectedError
		if errors.As(err, &rejectedError) && (rejectedError.StatusCode == 401 || rejectedError.StatusCode == 403) {
			d.rejected[tokenHash] = selected.Payload.ExpiresAt
		}
		d.scheduleRetry(now)
		d.recordError(err)
		return true, err
	}
	if dryRun {
		logf("verified token from %s; dry-run skips upload", selected.Source)
		return true, nil
	}

	changed, err := uploadToken(d.config, selected, d.cleanupRemote)
	if err != nil {
		d.scheduleRetry(now)
		d.recordError(err)
		return true, err
	}

	d.retryDelay = d.config.RetryMin
	d.nextAttempt = time.Time{}
	d.state.UploadedTokenSHA256 = tokenHash
	d.state.UploadedExpiresAt = selected.Payload.ExpiresAt
	d.state.LastSuccessAt = now.Unix()
	d.state.LastError = ""
	if err = writeState(d.config.StateFile, d.state); err != nil {
		return true, err
	}
	if changed {
		logf("uploaded verified China token from %s; expires_at=%d", selected.Source, selected.Payload.ExpiresAt)
	} else {
		logf("remote token is already current; expires_at=%d", selected.Payload.ExpiresAt)
	}
	return true, nil
}

func (d *daemon) scanAndStage(ctx context.Context, scanFile string) error {
	now := time.Now()
	files := []string{scanFile}
	if scanFile == "" {
		files = discoverPackageStorageFiles(androidUserRoot, chinaPackageName)
	}
	candidates, err := scanCandidateFiles(d.config, files)
	if err != nil {
		return err
	}
	d.state.LastScanAt = now.Unix()
	if len(candidates) == 0 {
		_ = writeState(d.config.StateFile, d.state)
		printResult(map[string]any{
			"ok": false, "found": false, "pending": d.state.PendingToken != "",
			"expires_at": d.state.PendingExpiresAt, "message": "本轮未检测到新的有效国服 Token",
		})
		return errors.New("未检测到有效国服 Token")
	}
	return d.stageCandidate(ctx, candidates[0])
}

func (d *daemon) watchAndStage(parent context.Context) error {
	ctx := parent
	cancel := func() {}
	if d.config.WatchTimeout > 0 {
		ctx, cancel = context.WithTimeout(parent, d.config.WatchTimeout)
	}
	defer cancel()

	started := time.Now()
	d.state.LastScanAt = started.Unix()
	_ = writeState(d.config.StateFile, d.state)
	printResult(map[string]any{
		"ok": true, "watching": true, "timeout_seconds": int64(d.config.WatchTimeout / time.Second),
		"message": "持续监听已开始；现在从国服 Lanota 打开 Portal",
	})

	connections := make(map[string]*webSocketConnection)
	defer func() {
		for _, connection := range connections {
			_ = connection.Close()
		}
	}()

	lastFileScan := time.Time{}
	lastSocketRefresh := time.Time{}
	for {
		if err := ctx.Err(); err != nil {
			if errors.Is(err, context.DeadlineExceeded) {
				printResult(map[string]any{
					"ok": false, "found": false, "pending": d.state.PendingToken != "",
					"message": "持续监听超时，请重新点击开始扫描",
				})
				return errors.New("持续监听超时")
			}
			return err
		}

		now := time.Now()
		if lastSocketRefresh.IsZero() || now.Sub(lastSocketRefresh) >= devToolsPollTime {
			for _, socketName := range discoverDevToolsSockets() {
				targets, listErr := listDevToolsTargets(ctx, socketName)
				if listErr != nil {
					continue
				}
				for _, target := range targets {
					if target.WebSocketDebuggerURL == "" || !isInspectableTarget(target) {
						continue
					}
					key := socketName + "\x00" + target.ID
					if existing := connections[key]; existing != nil {
						existing.targetURL = target.URL
						if strings.Contains(strings.ToLower(target.URL), portalHost) &&
							time.Since(existing.lastEvaluate) >= devToolsEvalTime {
							_ = existing.evaluateLocalStorage()
						}
						continue
					}
					connection, connectErr := connectDevToolsTarget(ctx, socketName, target)
					if connectErr == nil {
						connections[key] = connection
						printResult(map[string]any{
							"ok": true, "watching": true, "source": socketName,
							"message": "已连接浏览器调试通道，正在捕获 Portal 请求",
						})
					}
				}
			}
			lastSocketRefresh = now
		}

		for key, connection := range connections {
			item, readErr := connection.ReadCandidate(time.Now().Add(20 * time.Millisecond))
			if readErr != nil {
				if errors.Is(readErr, os.ErrDeadlineExceeded) || isTemporaryNetError(readErr) {
					continue
				}
				_ = connection.Close()
				delete(connections, key)
				continue
			}
			if item != nil {
				return d.stageCandidate(ctx, *item)
			}
		}

		if lastFileScan.IsZero() || now.Sub(lastFileScan) >= time.Second {
			files := discoverStorageFiles(androidUserRoot, storagePackageNames)
			items, scanErr := scanCandidateFiles(d.config, files)
			if scanErr == nil && len(items) > 0 {
				return d.stageCandidate(ctx, items[0])
			}
			lastFileScan = now
		}

		time.Sleep(devToolsPollTime)
	}
}

func (d *daemon) stageCandidate(ctx context.Context, selected candidate) error {
	if err := verifyPortalToken(ctx, d.config, selected.Token); err != nil {
		return err
	}
	d.state.LastScanAt = time.Now().Unix()
	d.state.PendingToken = selected.Token
	d.state.PendingSubject = selected.Payload.Subject
	d.state.PendingExpiresAt = selected.Payload.ExpiresAt
	d.state.PendingSource = selected.Source
	d.state.LastError = ""
	if err := writeState(d.config.StateFile, d.state); err != nil {
		return err
	}
	printResult(map[string]any{
		"ok": true, "found": true, "subject": selected.Payload.Subject,
		"expires_at": selected.Payload.ExpiresAt, "source": selected.Source,
		"message": "已捕获并验证，可点击上传",
	})
	return nil
}

func discoverDevToolsSockets() []string {
	result := map[string]struct{}{"chrome_devtools_remote": {}}
	raw, err := os.ReadFile("/proc/net/unix")
	if err == nil {
		for _, socketName := range parseDevToolsSockets(string(raw)) {
			result[socketName] = struct{}{}
		}
	}
	sockets := make([]string, 0, len(result))
	for socketName := range result {
		sockets = append(sockets, socketName)
	}
	sort.Strings(sockets)
	return sockets
}

func parseDevToolsSockets(raw string) []string {
	unique := make(map[string]struct{})
	for _, line := range strings.Split(raw, "\n") {
		matched := devToolsSocketPattern.FindStringSubmatch(line)
		if len(matched) == 2 && matched[1] != "" {
			unique[matched[1]] = struct{}{}
		}
	}
	result := make([]string, 0, len(unique))
	for socketName := range unique {
		result = append(result, socketName)
	}
	sort.Strings(result)
	return result
}

func listDevToolsTargets(ctx context.Context, socketName string) ([]devToolsTarget, error) {
	for _, endpoint := range []string{"/json/list", "/json"} {
		raw, err := devToolsHTTPRequest(ctx, socketName, endpoint)
		if err != nil {
			continue
		}
		var targets []devToolsTarget
		if json.Unmarshal(raw, &targets) == nil {
			return targets, nil
		}
	}
	return nil, errors.New("DevTools target list unavailable")
}

func devToolsHTTPRequest(ctx context.Context, socketName string, endpoint string) ([]byte, error) {
	connection, err := dialAbstractSocket(ctx, socketName)
	if err != nil {
		return nil, err
	}
	defer connection.Close()
	deadline := time.Now().Add(time.Second)
	if contextDeadline, ok := ctx.Deadline(); ok && contextDeadline.Before(deadline) {
		deadline = contextDeadline
	}
	_ = connection.SetDeadline(deadline)
	request := "GET " + endpoint + " HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n"
	if _, err = io.WriteString(connection, request); err != nil {
		return nil, err
	}
	response, err := http.ReadResponse(bufio.NewReader(connection), nil)
	if err != nil {
		return nil, err
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("DevTools HTTP %d", response.StatusCode)
	}
	return io.ReadAll(io.LimitReader(response.Body, 2*1024*1024))
}

func dialAbstractSocket(ctx context.Context, socketName string) (net.Conn, error) {
	name := strings.TrimPrefix(strings.TrimSpace(socketName), "@")
	if name == "" {
		return nil, errors.New("empty abstract socket name")
	}
	dialer := net.Dialer{Timeout: time.Second}
	return dialer.DialContext(ctx, "unix", "@"+name)
}

func isInspectableTarget(target devToolsTarget) bool {
	if target.Type != "" && target.Type != "page" && target.Type != "webview" {
		return false
	}
	return true
}

func connectDevToolsTarget(ctx context.Context, socketName string, target devToolsTarget) (*webSocketConnection, error) {
	parsed, err := url.Parse(target.WebSocketDebuggerURL)
	if err != nil || parsed.Path == "" {
		return nil, errors.New("invalid DevTools WebSocket URL")
	}
	connection, err := dialAbstractSocket(ctx, socketName)
	if err != nil {
		return nil, err
	}
	webSocket := &webSocketConnection{conn: connection, reader: bufio.NewReader(connection), targetURL: target.URL}
	if err = webSocket.handshake(parsed); err != nil {
		connection.Close()
		return nil, err
	}
	if err = webSocket.enableCapture(); err != nil {
		connection.Close()
		return nil, err
	}
	return webSocket, nil
}

func (connection *webSocketConnection) handshake(parsed *url.URL) error {
	keyBytes := make([]byte, 16)
	if _, err := rand.Read(keyBytes); err != nil {
		return err
	}
	request := &http.Request{
		Method: http.MethodGet,
		URL:    &url.URL{Path: parsed.Path, RawQuery: parsed.RawQuery},
		Host:   "localhost",
		Header: http.Header{
			"Connection":            []string{"Upgrade"},
			"Upgrade":               []string{"websocket"},
			"Sec-Websocket-Key":     []string{base64.StdEncoding.EncodeToString(keyBytes)},
			"Sec-Websocket-Version": []string{"13"},
		},
	}
	if request.URL.Path == "" {
		request.URL.Path = "/"
	}
	deadline := time.Now().Add(2 * time.Second)
	_ = connection.conn.SetDeadline(deadline)
	if err := request.Write(connection.conn); err != nil {
		return err
	}
	response, err := http.ReadResponse(connection.reader, request)
	if err != nil {
		return err
	}
	if response.StatusCode != http.StatusSwitchingProtocols {
		response.Body.Close()
		return fmt.Errorf("DevTools WebSocket upgrade failed: HTTP %d", response.StatusCode)
	}
	_ = connection.conn.SetDeadline(time.Time{})
	return nil
}

func (connection *webSocketConnection) enableCapture() error {
	if err := connection.sendCommand("Network.enable", nil); err != nil {
		return err
	}
	if err := connection.sendCommand("Runtime.enable", nil); err != nil {
		return err
	}
	return connection.evaluateLocalStorage()
}

func (connection *webSocketConnection) evaluateLocalStorage() error {
	expression := fmt.Sprintf(
		"JSON.stringify({token:localStorage.getItem(%q),user:localStorage.getItem(%q),href:location.href})",
		tokenStorageKey,
		userStorageKey,
	)
	err := connection.sendCommand("Runtime.evaluate", map[string]any{
		"expression": expression, "returnByValue": true,
	})
	if err == nil {
		connection.lastEvaluate = time.Now()
	}
	return err
}

func (connection *webSocketConnection) sendCommand(method string, params map[string]any) error {
	connection.writeMu.Lock()
	defer connection.writeMu.Unlock()
	connection.nextID++
	payload := map[string]any{"id": connection.nextID, "method": method}
	if params != nil {
		payload["params"] = params
	}
	raw, err := json.Marshal(payload)
	if err != nil {
		return err
	}
	return connection.writeFrame(0x1, raw)
}

func (connection *webSocketConnection) ReadCandidate(deadline time.Time) (*candidate, error) {
	_ = connection.conn.SetReadDeadline(deadline)
	for {
		opcode, raw, err := connection.readFrame()
		if err != nil {
			return nil, err
		}
		switch opcode {
		case 0x8:
			return nil, io.EOF
		case 0x9:
			if err = connection.writeFrame(0xA, raw); err != nil {
				return nil, err
			}
			continue
		case 0x1:
			return candidateFromDevToolsMessage(raw, connection.targetURL), nil
		default:
			continue
		}
	}
}

func candidateFromDevToolsMessage(raw []byte, targetURL string) *candidate {
	var message devToolsMessage
	if json.Unmarshal(raw, &message) != nil {
		return nil
	}
	sources := make([]string, 0, 4)
	sourceLabel := "DevTools " + targetURL
	if message.Method == "" && len(message.Result) > 0 {
		if !strings.Contains(strings.ToLower(targetURL), portalHost) {
			return nil
		}
		var evaluated struct {
			Result struct {
				Value string `json:"value"`
			} `json:"result"`
		}
		if json.Unmarshal(message.Result, &evaluated) == nil && evaluated.Result.Value != "" {
			sources = append(sources, evaluated.Result.Value)
			sourceLabel = "DevTools localStorage"
		}
	}
	if message.Method == "Network.requestWillBeSent" {
		var event networkRequestEvent
		if json.Unmarshal(message.Params, &event) == nil {
			if event.Request.URL != "" && !strings.Contains(strings.ToLower(event.Request.URL), portalHost) {
				return nil
			}
			sources = append(sources, event.Request.URL, event.Request.PostData)
			for key, value := range event.Request.Headers {
				sources = append(sources, key, fmt.Sprint(value))
			}
			sourceLabel = "DevTools Network.requestWillBeSent"
		}
	}
	for _, source := range sources {
		for _, token := range jwtPattern.FindAllString(source, -1) {
			payload, valid := parseChinaJWT(token, time.Now().Unix())
			if valid {
				return &candidate{Token: token, Payload: payload, Source: sourceLabel}
			}
		}
	}
	return nil
}

func (connection *webSocketConnection) writeFrame(opcode byte, payload []byte) error {
	header := []byte{0x80 | opcode}
	length := len(payload)
	switch {
	case length < 126:
		header = append(header, byte(0x80|length))
	case length <= 65535:
		header = append(header, 0x80|126, byte(length>>8), byte(length))
	default:
		header = append(header, 0x80|127)
		encoded := make([]byte, 8)
		binary.BigEndian.PutUint64(encoded, uint64(length))
		header = append(header, encoded...)
	}
	mask := make([]byte, 4)
	if _, err := rand.Read(mask); err != nil {
		return err
	}
	header = append(header, mask...)
	masked := make([]byte, len(payload))
	for index := range payload {
		masked[index] = payload[index] ^ mask[index%4]
	}
	if _, err := connection.conn.Write(header); err != nil {
		return err
	}
	_, err := connection.conn.Write(masked)
	return err
}

func (connection *webSocketConnection) readFrame() (byte, []byte, error) {
	header := make([]byte, 2)
	if _, err := io.ReadFull(connection.reader, header); err != nil {
		return 0, nil, err
	}
	opcode := header[0] & 0x0f
	length := uint64(header[1] & 0x7f)
	switch length {
	case 126:
		extended := make([]byte, 2)
		if _, err := io.ReadFull(connection.reader, extended); err != nil {
			return 0, nil, err
		}
		length = uint64(binary.BigEndian.Uint16(extended))
	case 127:
		extended := make([]byte, 8)
		if _, err := io.ReadFull(connection.reader, extended); err != nil {
			return 0, nil, err
		}
		length = binary.BigEndian.Uint64(extended)
	}
	if length > 16*1024*1024 {
		return 0, nil, errors.New("DevTools WebSocket frame too large")
	}
	masked := header[1]&0x80 != 0
	mask := make([]byte, 4)
	if masked {
		if _, err := io.ReadFull(connection.reader, mask); err != nil {
			return 0, nil, err
		}
	}
	payload := make([]byte, int(length))
	if _, err := io.ReadFull(connection.reader, payload); err != nil {
		return 0, nil, err
	}
	if masked {
		for index := range payload {
			payload[index] ^= mask[index%4]
		}
	}
	return opcode, payload, nil
}

func (connection *webSocketConnection) Close() error {
	return connection.conn.Close()
}

func isTemporaryNetError(err error) bool {
	var netErr net.Error
	return errors.As(err, &netErr) && netErr.Timeout()
}

func (d *daemon) uploadPending(ctx context.Context) error {
	if d.state.PendingToken == "" || d.state.PendingExpiresAt <= time.Now().Unix() {
		return errors.New("没有可上传的有效 Token，请先开始扫描")
	}
	if err := verifyPortalToken(ctx, d.config, d.state.PendingToken); err != nil {
		return err
	}
	item := candidate{Token: d.state.PendingToken, Payload: jwtPayload{
		Issuer: "lanota-portal", Subject: d.state.PendingSubject, ExpiresAt: d.state.PendingExpiresAt,
	}, Source: d.state.PendingSource}
	changed, err := uploadToken(d.config, item, d.cleanupRemote)
	if err != nil {
		return err
	}
	d.state.UploadedTokenSHA256 = tokenSHA256(item.Token)
	d.state.UploadedExpiresAt = item.Payload.ExpiresAt
	d.state.LastSuccessAt = time.Now().Unix()
	d.state.LastError = ""
	if err = writeState(d.config.StateFile, d.state); err != nil {
		return err
	}
	printResult(map[string]any{"ok": true, "uploaded": true, "changed": changed, "expires_at": item.Payload.ExpiresAt, "message": "上传成功"})
	return nil
}

func printStatus(state daemonState) {
	printResult(map[string]any{
		"ok": true, "pending": state.PendingToken != "", "subject": state.PendingSubject,
		"expires_at": state.PendingExpiresAt, "source": state.PendingSource,
		"uploaded_expires_at": state.UploadedExpiresAt, "last_success_at": state.LastSuccessAt,
		"last_error": state.LastError,
	})
}

func printResult(result map[string]any) {
	raw, err := json.Marshal(result)
	if err == nil {
		fmt.Println(string(raw))
	}
}

func discoverPackageStorageFiles(userRoot string, packageName string) []string {
	return discoverStorageFiles(userRoot, []string{packageName})
}

func discoverStorageFiles(userRoot string, packageNames []string) []string {
	files := make([]string, 0)
	packageRoots := make([]string, 0)
	for _, packageName := range packageNames {
		matched, _ := filepath.Glob(filepath.Join(userRoot, "*", packageName))
		packageRoots = append(packageRoots, matched...)
	}
	for _, root := range packageRoots {
		_ = filepath.WalkDir(root, func(fileName string, entry fs.DirEntry, walkErr error) error {
			if walkErr != nil {
				return nil
			}
			if entry.IsDir() {
				relative, relErr := filepath.Rel(root, fileName)
				if relErr != nil || relative == "." {
					return nil
				}
				parts := strings.Split(filepath.ToSlash(relative), "/")
				if len(parts) == 1 && !strings.HasPrefix(strings.ToLower(parts[0]), "app_") {
					return filepath.SkipDir
				}
				switch strings.ToLower(entry.Name()) {
				case "cache", "code cache", "gpucache", "indexeddb", "service worker", "session storage":
					return filepath.SkipDir
				}
				return nil
			}
			normalized := strings.ToLower(filepath.ToSlash(fileName))
			if strings.Contains(normalized, "/local storage/leveldb/") ||
				strings.Contains(normalized, "/localstorage/") {
				files = append(files, fileName)
			}
			return nil
		})
	}
	return files
}

func scanCandidateFiles(cfg config, files []string) ([]candidate, error) {
	unique := make(map[string]candidate)
	now := time.Now().Unix()
	for _, fileName := range files {
		info, err := os.Stat(fileName)
		if err != nil || info.Size() <= 0 || info.Size() > cfg.MaxFileBytes {
			continue
		}
		raw, err := os.ReadFile(fileName)
		if err != nil {
			continue
		}
		for _, source := range [][]byte{raw, bytes.ReplaceAll(raw, []byte{0}, nil)} {
			for _, match := range jwtPattern.FindAll(source, -1) {
				token := string(match)
				payload, valid := parseChinaJWT(token, now)
				if !valid {
					continue
				}
				unique[tokenSHA256(token)] = candidate{Token: token, Payload: payload, Source: fileName}
			}
		}
	}

	result := make([]candidate, 0, len(unique))
	for _, item := range unique {
		result = append(result, item)
	}
	sort.Slice(result, func(i, j int) bool {
		if result[i].Payload.IssuedAt == result[j].Payload.IssuedAt {
			return result[i].Payload.ExpiresAt > result[j].Payload.ExpiresAt
		}
		return result[i].Payload.IssuedAt > result[j].Payload.IssuedAt
	})
	return result, nil
}

type portalRejectedError struct {
	StatusCode int
}

func (err portalRejectedError) Error() string {
	return fmt.Sprintf("Portal rejected token: HTTP %d", err.StatusCode)
}

func parseChinaJWT(token string, now int64) (jwtPayload, bool) {
	parts := strings.Split(token, ".")
	if len(parts) != 3 {
		return jwtPayload{}, false
	}
	var header jwtHeader
	if err := decodeJWTPart(parts[0], &header); err != nil || header.Algorithm != "HS256" {
		return jwtPayload{}, false
	}
	var payload jwtPayload
	if err := decodeJWTPart(parts[1], &payload); err != nil {
		return jwtPayload{}, false
	}
	if payload.Issuer != "lanota-portal" || payload.Subject == "" || payload.ExpiresAt <= now {
		return jwtPayload{}, false
	}
	return payload, true
}

func decodeJWTPart(value string, target any) error {
	raw, err := base64.RawURLEncoding.DecodeString(value)
	if err != nil {
		return err
	}
	return json.Unmarshal(raw, target)
}

func verifyPortalToken(parent context.Context, cfg config, token string) error {
	ctx, cancel := context.WithTimeout(parent, cfg.ConnectTimeout)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, cfg.PortalMeURL, nil)
	if err != nil {
		return err
	}
	req.Header.Set("Authorization", "Bearer "+token)
	req.Header.Set("Accept", "application/json")
	req.Header.Set("User-Agent", userAgent)
	response, err := http.DefaultClient.Do(req)
	if err != nil {
		return fmt.Errorf("Portal verification request failed: %w", err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		_, _ = io.Copy(io.Discard, io.LimitReader(response.Body, 4096))
		return portalRejectedError{StatusCode: response.StatusCode}
	}
	var data map[string]any
	if err = json.NewDecoder(io.LimitReader(response.Body, 1024*1024)).Decode(&data); err != nil || data == nil {
		return errors.New("Portal /api/me returned invalid JSON")
	}
	return nil
}

func uploadToken(cfg config, item candidate, cleanupRemote bool) (bool, error) {
	client, sftpClient, err := connectSFTP(cfg)
	if err != nil {
		return false, err
	}
	defer client.Close()
	defer sftpClient.Close()

	if current, readErr := readRemoteFile(sftpClient, cfg.RemotePath, 1024*1024); readErr == nil {
		var existing authFile
		if json.Unmarshal(current, &existing) == nil && existing.ChinaToken == item.Token {
			return false, nil
		}
	}

	payload := authFile{
		ChinaToken: item.Token,
		UID:        item.Payload.Subject,
		ExpiresAt:  item.Payload.ExpiresAt,
		SavedAt:    time.Now().Unix(),
	}
	raw, err := json.MarshalIndent(payload, "", "  ")
	if err != nil {
		return false, err
	}
	raw = append(raw, '\n')
	if err = replaceRemoteFile(sftpClient, cfg.RemotePath, raw); err != nil {
		return false, err
	}
	if cleanupRemote {
		uploaded, readErr := readRemoteFile(sftpClient, cfg.RemotePath, int64(len(raw)+1))
		if readErr != nil || !bytes.Equal(uploaded, raw) {
			return false, errors.New("diagnostic remote file verification failed")
		}
		if removeErr := sftpClient.Remove(cfg.RemotePath); removeErr != nil {
			return false, fmt.Errorf("remove diagnostic remote file: %w", removeErr)
		}
		_ = sftpClient.Remove(cfg.RemotePath + ".bak")
		logf("diagnostic remote upload verified and removed")
	}
	return true, nil
}

func connectSFTP(cfg config) (*ssh.Client, *sftp.Client, error) {
	address := net.JoinHostPort(cfg.ServerHost, strconv.Itoa(cfg.ServerPort))
	connection, err := net.DialTimeout("tcp", address, cfg.ConnectTimeout)
	if err != nil {
		return nil, nil, fmt.Errorf("SSH connection failed: %w", err)
	}
	deadline := time.Now().Add(cfg.ConnectTimeout)
	_ = connection.SetDeadline(deadline)
	sshConfig := &ssh.ClientConfig{
		User:    cfg.ServerUser,
		Auth:    []ssh.AuthMethod{ssh.Password(cfg.ServerPassword)},
		Timeout: cfg.ConnectTimeout,
		HostKeyCallback: func(_ string, _ net.Addr, key ssh.PublicKey) error {
			actual := ssh.FingerprintSHA256(key)
			if actual != cfg.ServerHostKeySHA256 {
				return fmt.Errorf("SSH host key mismatch: got %s", actual)
			}
			return nil
		},
	}
	sshConnection, channels, requests, err := ssh.NewClientConn(connection, address, sshConfig)
	if err != nil {
		connection.Close()
		return nil, nil, fmt.Errorf("SSH authentication failed: %w", err)
	}
	_ = connection.SetDeadline(time.Now().Add(2 * cfg.ConnectTimeout))
	client := ssh.NewClient(sshConnection, channels, requests)
	sftpClient, err := sftp.NewClient(client, sftp.UseConcurrentReads(false), sftp.UseConcurrentWrites(false))
	if err != nil {
		client.Close()
		return nil, nil, fmt.Errorf("SFTP subsystem failed: %w", err)
	}
	return client, sftpClient, nil
}

func replaceRemoteFile(client *sftp.Client, target string, raw []byte) error {
	directory := path.Dir(strings.ReplaceAll(target, "\\", "/"))
	if err := client.MkdirAll(directory); err != nil {
		return fmt.Errorf("create remote directory: %w", err)
	}
	timestamp := strconv.FormatInt(time.Now().UnixNano(), 10)
	temporary := target + ".uploading." + timestamp
	backupTemp := target + ".bak.uploading." + timestamp
	backup := target + ".bak"
	rollback := target + ".rollback." + timestamp

	if err := writeRemoteFile(client, temporary, raw); err != nil {
		return err
	}
	defer client.Remove(temporary)
	written, err := readRemoteFile(client, temporary, int64(len(raw)+1))
	if err != nil || !bytes.Equal(written, raw) {
		return errors.New("uploaded temporary file verification failed")
	}

	existing, existingErr := readRemoteFile(client, target, 1024*1024)
	if existingErr == nil {
		if err = writeRemoteFile(client, backupTemp, existing); err != nil {
			return fmt.Errorf("write backup: %w", err)
		}
		_ = client.Remove(backup)
		if err = client.Rename(backupTemp, backup); err != nil {
			_ = client.Remove(backupTemp)
			return fmt.Errorf("activate backup: %w", err)
		}
	}

	if err = client.PosixRename(temporary, target); err == nil {
		return nil
	}
	if _, statErr := client.Stat(target); statErr == nil {
		if err = client.Rename(target, rollback); err != nil {
			return fmt.Errorf("prepare remote replacement: %w", err)
		}
		if err = client.Rename(temporary, target); err != nil {
			_ = client.Rename(rollback, target)
			return fmt.Errorf("activate remote file: %w", err)
		}
		_ = client.Remove(rollback)
		return nil
	}
	if err = client.Rename(temporary, target); err != nil {
		return fmt.Errorf("activate new remote file: %w", err)
	}
	return nil
}

func writeRemoteFile(client *sftp.Client, fileName string, raw []byte) error {
	file, err := client.OpenFile(fileName, os.O_WRONLY|os.O_CREATE|os.O_TRUNC)
	if err != nil {
		return err
	}
	_, writeErr := file.Write(raw)
	closeErr := file.Close()
	if writeErr != nil {
		return writeErr
	}
	return closeErr
}

func readRemoteFile(client *sftp.Client, fileName string, limit int64) ([]byte, error) {
	file, err := client.Open(fileName)
	if err != nil {
		return nil, err
	}
	defer file.Close()
	return io.ReadAll(io.LimitReader(file, limit))
}

func tokenSHA256(token string) string {
	digest := sha256.Sum256([]byte(token))
	return hex.EncodeToString(digest[:])
}

func readState(fileName string) daemonState {
	raw, err := os.ReadFile(fileName)
	if err != nil {
		return daemonState{}
	}
	var result daemonState
	if json.Unmarshal(raw, &result) != nil {
		return daemonState{}
	}
	return result
}

func writeState(fileName string, state daemonState) error {
	raw, err := json.MarshalIndent(state, "", "  ")
	if err != nil {
		return err
	}
	if err = os.MkdirAll(filepath.Dir(fileName), 0700); err != nil {
		return err
	}
	temporary := fileName + ".tmp"
	if err = os.WriteFile(temporary, append(raw, '\n'), 0600); err != nil {
		return err
	}
	return os.Rename(temporary, fileName)
}

func (d *daemon) recordError(err error) {
	d.state.LastErrorAt = time.Now().Unix()
	d.state.LastError = err.Error()
	_ = writeState(d.config.StateFile, d.state)
}

func (d *daemon) scheduleRetry(now time.Time) {
	d.nextAttempt = now.Add(d.retryDelay)
	d.retryDelay *= 2
	if d.retryDelay > d.config.RetryMax {
		d.retryDelay = d.config.RetryMax
	}
}

func logf(format string, arguments ...any) {
	fmt.Printf("%s %s\n", time.Now().Format("2006-01-02 15:04:05"), fmt.Sprintf(format, arguments...))
}

func fatalf(format string, arguments ...any) {
	logf(format, arguments...)
	os.Exit(1)
}
