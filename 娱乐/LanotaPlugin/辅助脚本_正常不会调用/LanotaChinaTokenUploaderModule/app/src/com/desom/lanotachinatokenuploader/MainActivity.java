package com.desom.lanotachinatokenuploader;

import android.app.Activity;
import android.graphics.Color;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import org.json.JSONObject;

public final class MainActivity extends Activity {
    private static final String MODULE = "/data/adb/modules/lanota_china_token_uploader";
    private static final String DAEMON = MODULE + "/bin/lanota-token-daemon";
    private static final String CONFIG = MODULE + "/config.conf";
    private final Handler handler = new Handler(Looper.getMainLooper());
    private TextView status;
    private Button scanButton;
    private Button uploadButton;
    private Button clearButton;
    private Button authorizeButton;
    private Process runningProcess;
    private volatile boolean scanning;
    private volatile boolean busy;
    private volatile boolean pendingAvailable;

    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        buildLayout();
        runCommand("status");
    }

    private void buildLayout() {
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(28, 28, 28, 20);

        TextView title = new TextView(this);
        title.setText("Lanota 国服 Token 控制台");
        title.setTextSize(22);
        title.setTextColor(Color.rgb(30, 30, 30));
        root.addView(title, new LinearLayout.LayoutParams(-1, -2));

        TextView hint = new TextView(this);
        hint.setText("一键授权上传会自动唤醒 Lanota 并完成 Token 获取与上传。");
        hint.setTextSize(14);
        root.addView(hint, new LinearLayout.LayoutParams(-1, -2));

        authorizeButton = new Button(this);
        authorizeButton.setText("一键授权上传");
        authorizeButton.setOnClickListener(v -> runCommand("authorize"));
        root.addView(authorizeButton, new LinearLayout.LayoutParams(-1, -2));

        LinearLayout actions = new LinearLayout(this);
        actions.setOrientation(LinearLayout.HORIZONTAL);
        scanButton = new Button(this);
        scanButton.setText("开始扫描");
        scanButton.setOnClickListener(v -> {
            if (scanning) {
                scanning = false;
                if (runningProcess != null) {
                    runningProcess.destroy();
                }
                scanButton.setEnabled(false);
                status.setText("正在停止扫描...\n");
            } else {
                if (busy) {
                    return;
                }
                scanning = true;
                scanButton.setText("停止扫描");
                runCommand("scan");
            }
        });
        uploadButton = new Button(this);
        uploadButton.setText("上传 Token");
        uploadButton.setEnabled(false);
        uploadButton.setOnClickListener(v -> runCommand("upload"));
        clearButton = new Button(this);
        clearButton.setText("清除待上传");
        clearButton.setOnClickListener(v -> runCommand("clear"));
        actions.addView(scanButton, new LinearLayout.LayoutParams(0, -2, 1));
        actions.addView(uploadButton, new LinearLayout.LayoutParams(0, -2, 1));
        actions.addView(clearButton, new LinearLayout.LayoutParams(0, -2, 1));
        root.addView(actions);

        status = new TextView(this);
        status.setTextSize(14);
        status.setTextColor(Color.DKGRAY);
        status.setPadding(4, 16, 4, 16);
        ScrollView scroll = new ScrollView(this);
        scroll.addView(status);
        root.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));
        setContentView(root);
    }

    private void runCommand(final String command) {
        if (busy) {
            return;
        }
        busy = true;
        scanButton.setEnabled(command.equals("scan"));
        uploadButton.setEnabled(false);
        clearButton.setEnabled(false);
        authorizeButton.setEnabled(false);
        status.setText(command.equals("scan")
                ? "正在启动捕获，请从国服 Lanota 打开 Portal...\n"
                : command.equals("authorize")
                ? "正在唤醒 Lanota 并创建授权会话...\n"
                : "正在执行 " + command + "...\n");
        Thread worker = new Thread(() -> {
            Process process = null;
            String resultText = "";
            try {
                String lastLine = "";
                String shell = DAEMON + " -config " + CONFIG + " -command " + command;
                process = new ProcessBuilder("su", "-c", shell).redirectErrorStream(true).start();
                runningProcess = process;
                BufferedReader reader = new BufferedReader(new InputStreamReader(process.getInputStream()));
                String line;
                while ((line = reader.readLine()) != null) {
                    lastLine = line;
                    final String display = humanMessage(line);
                    handler.post(() -> status.setText(display));
                }
                process.waitFor();
                resultText = lastLine;
            } catch (IOException | InterruptedException e) {
                resultText = "执行失败：" + e.getMessage() + "\n";
            } finally {
                if (process != null) {
                    process.destroy();
                }
                runningProcess = null;
                busy = false;
                final String result = resultText;
                handler.post(() -> {
                    if (command.equals("scan") && !result.contains("\"found\":true") && !result.contains("\"pending\":true")) {
                        status.setText("未捕获到 Token，扫描已结束");
                    } else {
                        status.setText(result.length() == 0 ? "没有返回结果" : humanMessage(result));
                    }
                    scanButton.setEnabled(true);
                    scanButton.setText("开始扫描");
                    scanning = false;
                    clearButton.setEnabled(true);
                    authorizeButton.setEnabled(true);
                    if (result.contains("\"pending\":true") || result.contains("\"found\":true") || result.contains("\"uploaded\":true")) {
                        pendingAvailable = true;
                    } else if (command.equals("clear") || command.equals("status")) {
                        pendingAvailable = false;
                    }
                    uploadButton.setEnabled(pendingAvailable);
                });
            }
        });
        worker.start();
    }

    private String humanMessage(String rawLine) {
        String line = rawLine == null ? "" : rawLine.trim();
        if (!line.startsWith("{")) {
            return line;
        }
        try {
            JSONObject json = new JSONObject(line);
            String message = json.optString("message", "");
            if (!message.isEmpty()) {
                return message;
            }
        } catch (Exception ignored) {
        }
        return line;
    }

    @Override
    protected void onDestroy() {
        if (runningProcess != null) {
            scanning = false;
            runningProcess.destroy();
        }
        super.onDestroy();
    }
}
