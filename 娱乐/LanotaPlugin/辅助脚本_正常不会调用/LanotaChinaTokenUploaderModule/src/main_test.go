package main

import (
	"bufio"
	"bytes"
	"crypto/rand"
	"crypto/rsa"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func testToken(issuer string, expiresAt int64) string {
	header := base64.RawURLEncoding.EncodeToString([]byte(`{"alg":"HS256","typ":"JWT"}`))
	payload := base64.RawURLEncoding.EncodeToString([]byte(fmt.Sprintf(
		`{"iss":%q,"sub":"test-user","iat":1,"exp":%d}`,
		issuer,
		expiresAt,
	)))
	return header + "." + payload + ".abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG"
}

func TestParseChinaJWT(t *testing.T) {
	token := testToken("lanota-portal", time.Now().Add(time.Hour).Unix())
	payload, ok := parseChinaJWT(token, time.Now().Unix())
	if !ok || payload.Subject != "test-user" {
		t.Fatalf("expected valid China token, got %#v, %v", payload, ok)
	}
	if _, ok = parseChinaJWT(testToken("other", time.Now().Add(time.Hour).Unix()), time.Now().Unix()); ok {
		t.Fatal("accepted a non-China issuer")
	}
	if _, ok = parseChinaJWT(testToken("lanota-portal", time.Now().Add(-time.Hour).Unix()), time.Now().Unix()); ok {
		t.Fatal("accepted an expired token")
	}
}

func TestScanCandidatesHandlesNullBytes(t *testing.T) {
	token := testToken("lanota-portal", time.Now().Add(time.Hour).Unix())
	fileName := filepath.Join(t.TempDir(), "000001.log")
	raw := make([]byte, 0, len(token)*2)
	for _, character := range []byte(token) {
		raw = append(raw, character, 0)
	}
	if err := os.WriteFile(fileName, raw, 0600); err != nil {
		t.Fatal(err)
	}
	cfg := config{MaxFileBytes: 1024 * 1024}
	items, err := scanCandidateFiles(cfg, []string{fileName})
	if err != nil {
		t.Fatal(err)
	}
	if len(items) != 1 || items[0].Token != token {
		t.Fatalf("expected one token, got %#v", items)
	}
}

func TestDiscoverStorageFilesSkipsUnrelatedDirectories(t *testing.T) {
	userRoot := t.TempDir()
	root := filepath.Join(userRoot, "0", chinaPackageName)
	levelDB := filepath.Join(root, "app_webview", "Default", "Local Storage", "leveldb")
	cache := filepath.Join(root, "app_webview", "Default", "Cache")
	if err := os.MkdirAll(levelDB, 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.MkdirAll(cache, 0700); err != nil {
		t.Fatal(err)
	}
	wanted := filepath.Join(levelDB, "000001.log")
	ignored := filepath.Join(cache, "token.log")
	if err := os.WriteFile(wanted, []byte("wanted"), 0600); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(ignored, []byte("ignored"), 0600); err != nil {
		t.Fatal(err)
	}
	files := discoverPackageStorageFiles(userRoot, chinaPackageName)
	if len(files) != 1 || files[0] != wanted {
		t.Fatalf("expected only %s, got %#v", wanted, files)
	}
}

func TestDiscoverStorageFilesIgnoresOtherPackages(t *testing.T) {
	userRoot := t.TempDir()
	otherLevelDB := filepath.Join(userRoot, "0", "com.android.chrome", "app_chrome", "Default", "Local Storage", "leveldb")
	if err := os.MkdirAll(otherLevelDB, 0700); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(otherLevelDB, "000001.log"), []byte("ignored"), 0600); err != nil {
		t.Fatal(err)
	}
	if files := discoverPackageStorageFiles(userRoot, chinaPackageName); len(files) != 0 {
		t.Fatalf("expected other packages to be ignored, got %#v", files)
	}
}

func TestDiscoverStorageFilesIncludesBrowserFallback(t *testing.T) {
	userRoot := t.TempDir()
	levelDB := filepath.Join(userRoot, "0", "com.android.chrome", "app_chrome", "Default", "Local Storage", "leveldb")
	if err := os.MkdirAll(levelDB, 0700); err != nil {
		t.Fatal(err)
	}
	wanted := filepath.Join(levelDB, "000001.log")
	if err := os.WriteFile(wanted, []byte("wanted"), 0600); err != nil {
		t.Fatal(err)
	}
	files := discoverStorageFiles(userRoot, storagePackageNames)
	if len(files) != 1 || files[0] != wanted {
		t.Fatalf("expected browser Local Storage fallback, got %#v", files)
	}
}

func TestParseDevToolsSockets(t *testing.T) {
	raw := "Num RefCount Protocol Flags Type St Inode Path\n" +
		"0000000000000000: 00000002 00000000 00010000 0001 01 1 @chrome_devtools_remote\n" +
		"0000000000000000: 00000002 00000000 00010000 0001 01 2 @webview_devtools_remote_1234\n"
	sockets := parseDevToolsSockets(raw)
	if len(sockets) != 2 || sockets[0] != "chrome_devtools_remote" || sockets[1] != "webview_devtools_remote_1234" {
		t.Fatalf("unexpected DevTools sockets: %#v", sockets)
	}
}

func TestCandidateFromDevToolsNetworkRequest(t *testing.T) {
	token := testToken("lanota-portal", time.Now().Add(time.Hour).Unix())
	raw := []byte(fmt.Sprintf(
		`{"method":"Network.requestWillBeSent","params":{"request":{"url":"https://lanota.gmzon.com/portal/api/me","headers":{"Authorization":"Bearer %s"}}}}`,
		token,
	))
	item := candidateFromDevToolsMessage(raw, "https://lanota.gmzon.com/portal")
	if item == nil || item.Token != token || item.Source != "DevTools Network.requestWillBeSent" {
		t.Fatalf("expected network token, got %#v", item)
	}
}

func TestCandidateFromDevToolsLocalStorage(t *testing.T) {
	token := testToken("lanota-portal", time.Now().Add(time.Hour).Unix())
	value, err := json.Marshal(map[string]string{"token": token, "href": "https://lanota.gmzon.com/portal"})
	if err != nil {
		t.Fatal(err)
	}
	raw, err := json.Marshal(map[string]any{
		"id": 3,
		"result": map[string]any{
			"result": map[string]any{"type": "string", "value": string(value)},
		},
	})
	if err != nil {
		t.Fatal(err)
	}
	item := candidateFromDevToolsMessage(raw, "https://lanota.gmzon.com/portal")
	if item == nil || item.Token != token || item.Source != "DevTools localStorage" {
		t.Fatalf("expected localStorage token, got %#v", item)
	}
}

func TestNetworkRequestRejectsOtherHost(t *testing.T) {
	token := testToken("lanota-portal", time.Now().Add(time.Hour).Unix())
	raw := []byte(fmt.Sprintf(
		`{"method":"Network.requestWillBeSent","params":{"request":{"url":"https://example.com/","headers":{"Authorization":"Bearer %s"}}}}`,
		token,
	))
	if item := candidateFromDevToolsMessage(raw, "https://example.com/"); item != nil {
		t.Fatalf("accepted token from another request host: %#v", item)
	}
}

func TestWebSocketFrameReadAndWrite(t *testing.T) {
	client, server := net.Pipe()
	defer client.Close()
	defer server.Close()
	connection := &webSocketConnection{conn: client, reader: bufio.NewReader(client)}

	serverPayload := []byte(`{"id":1,"result":{}}`)
	go func() {
		_, _ = server.Write(append([]byte{0x81, byte(len(serverPayload))}, serverPayload...))
	}()
	opcode, received, err := connection.readFrame()
	if err != nil || opcode != 0x1 || !bytes.Equal(received, serverPayload) {
		t.Fatalf("unexpected server frame: opcode=%d payload=%q err=%v", opcode, received, err)
	}

	clientPayload := []byte(`{"id":2,"method":"Runtime.enable"}`)
	writeDone := make(chan error, 1)
	go func() {
		writeDone <- connection.writeFrame(0x1, clientPayload)
	}()
	header := make([]byte, 2)
	if _, err = io.ReadFull(server, header); err != nil {
		t.Fatal(err)
	}
	if header[0] != 0x81 || header[1]&0x80 == 0 {
		t.Fatalf("invalid client frame header: %v", header)
	}
	length := int(header[1] & 0x7f)
	mask := make([]byte, 4)
	masked := make([]byte, length)
	if _, err = io.ReadFull(server, mask); err != nil {
		t.Fatal(err)
	}
	if _, err = io.ReadFull(server, masked); err != nil {
		t.Fatal(err)
	}
	for index := range masked {
		masked[index] ^= mask[index%4]
	}
	if !bytes.Equal(masked, clientPayload) {
		t.Fatalf("unexpected client payload: %q", masked)
	}
	if err = <-writeDone; err != nil {
		t.Fatal(err)
	}
}

func TestADBPacketRoundTrip(t *testing.T) {
	client, server := net.Pipe()
	defer client.Close()
	defer server.Close()

	payload := []byte("localabstract:chrome_devtools_remote")
	go func() {
		_ = writeADBPacket(client, adbOPEN, 7, 0, payload)
	}()
	command, arg0, arg1, received, err := readADBPacket(server)
	if err != nil {
		t.Fatal(err)
	}
	if command != adbOPEN || arg0 != 7 || arg1 != 0 || !bytes.Equal(received, payload) {
		t.Fatalf("unexpected ADB packet: command=%d arg0=%d arg1=%d payload=%q", command, arg0, arg1, received)
	}
}

func TestAndroidPublicKeyEncoding(t *testing.T) {
	privateKey, err := rsa.GenerateKey(rand.Reader, 2048)
	if err != nil {
		t.Fatal(err)
	}
	raw, err := encodeAndroidPublicKey(&privateKey.PublicKey)
	if err != nil {
		t.Fatal(err)
	}
	if len(raw) != 524 {
		t.Fatalf("expected 524 byte Android public key, got %d", len(raw))
	}
	publicKey, err := androidPublicKeyString(privateKey)
	if err != nil {
		t.Fatal(err)
	}
	decoded, err := base64.StdEncoding.DecodeString(publicKey)
	if err != nil || len(decoded) != 524 {
		t.Fatalf("public key is not valid 524 byte base64: len=%d err=%v", len(decoded), err)
	}
}
