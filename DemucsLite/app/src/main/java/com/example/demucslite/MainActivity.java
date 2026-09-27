package com.example.demucslite;

import android.Manifest;
import android.app.Activity;
import android.app.DownloadManager;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.media.MediaPlayer;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.Environment;
import android.provider.OpenableColumns;
import android.view.View;
import android.widget.Button;
import android.widget.ProgressBar;
import android.widget.SeekBar;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONException;
import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.util.Locale;
import java.util.concurrent.atomic.AtomicInteger;

import okhttp3.Call;
import okhttp3.Callback;
import okhttp3.MediaType;
import okhttp3.MultipartBody;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;
import okhttp3.ResponseBody;

public class MainActivity extends Activity {

    private static final int REQUEST_PICK_AUDIO = 1001;
    private static final int REQUEST_WRITE_STORAGE = 1002;

    /*
     * Emulator:
     * 10.0.2.2 = localhost của máy tính đang chạy Android Studio.
     *
     * Điện thoại thật:
     * đổi sang IP LAN của máy chạy server.
     * Ví dụ:
     * http://192.168.1.10:8000
     */
    private static final String SERVER_BASE_URL =
            "http://127.0.0.1:8000";

    private static final String SEPARATE_ENDPOINT =
            SERVER_BASE_URL + "/separate";

    private final OkHttpClient httpClient =
            new OkHttpClient.Builder()
                    .retryOnConnectionFailure(true)
                    .build();

    private Uri selectedAudioUri;
    private final Handler statusHandler = new Handler(Looper.getMainLooper());
    private String activeJobId;
    private String selectedFileName = "song.wav";

    private Button btnChooseFile;
    private Button btnSeparate;

    private Button btnPlayAll;
    private Button btnStopAll;

    private TextView tvSelectedFile;
    private TextView tvStatus;

    private ProgressBar progressBar;

    private TrackUI vocals;
    private TrackUI drums;
    private TrackUI bass;
    private TrackUI other;

    private TrackUI[] tracks;

    @Override
    protected void onCreate(Bundle savedInstanceState) {

        super.onCreate(savedInstanceState);

        setContentView(R.layout.activity_main);

        bindViews();

        setupActions();

        requestLegacyStoragePermissionIfNeeded();
    }

    private void bindViews() {

        btnChooseFile =
                findViewById(R.id.btnChooseFile);

        btnSeparate =
                findViewById(R.id.btnSeparate);

        btnPlayAll =
                findViewById(R.id.btnPlayAll);

        btnStopAll =
                findViewById(R.id.btnStopAll);

        tvSelectedFile =
                findViewById(R.id.tvSelectedFile);

        tvStatus =
                findViewById(R.id.tvStatus);

        progressBar =
                findViewById(R.id.progressBar);


        vocals = new TrackUI(
                "vocals",
                "Vocals",
                findViewById(R.id.btnPlayVocals),
                findViewById(R.id.btnDownloadVocals),
                findViewById(R.id.sbVocals)
        );


        drums = new TrackUI(
                "drums",
                "Drums",
                findViewById(R.id.btnPlayDrums),
                findViewById(R.id.btnDownloadDrums),
                findViewById(R.id.sbDrums)
        );


        bass = new TrackUI(
                "bass",
                "Bass",
                findViewById(R.id.btnPlayBass),
                findViewById(R.id.btnDownloadBass),
                findViewById(R.id.sbBass)
        );


        other = new TrackUI(
                "other",
                "Other",
                findViewById(R.id.btnPlayOther),
                findViewById(R.id.btnDownloadOther),
                findViewById(R.id.sbOther)
        );


        tracks = new TrackUI[]{
                vocals,
                drums,
                bass,
                other
        };


        for (TrackUI track : tracks) {

            setupTrackControls(track);
        }
    }

    private void setupActions() {

        btnChooseFile.setOnClickListener(
                v -> openAudioPicker()
        );


        btnSeparate.setOnClickListener(
                v -> uploadAndSeparate()
        );


        btnPlayAll.setOnClickListener(
                v -> playAllTracks()
        );


        btnStopAll.setOnClickListener(
                v -> stopAllTracks()
        );
    }

    private void setupTrackControls(TrackUI track) {

        track.playButton.setOnClickListener(
                v -> toggleTrack(track)
        );


        track.downloadButton.setOnClickListener(
                v -> downloadTrack(track)
        );


        track.volumeSeekBar.setMax(100);

        track.volumeSeekBar.setProgress(100);


        track.volumeSeekBar.setOnSeekBarChangeListener(
                new SeekBar.OnSeekBarChangeListener() {

                    @Override
                    public void onProgressChanged(
                            SeekBar seekBar,
                            int progress,
                            boolean fromUser
                    ) {

                        float volume =
                                progress / 100f;

                        track.volume =
                                volume;


                        if (track.player != null) {

                            track.player.setVolume(
                                    volume,
                                    volume
                            );
                        }
                    }

                    @Override
                    public void onStartTrackingTouch(
                            SeekBar seekBar
                    ) {

                    }

                    @Override
                    public void onStopTrackingTouch(
                            SeekBar seekBar
                    ) {

                    }
                }
        );
    }

    // ============================
    // CHỌN FILE
    // ============================

    private void openAudioPicker() {

        Intent intent =
                new Intent(
                        Intent.ACTION_OPEN_DOCUMENT
                );

        intent.addCategory(
                Intent.CATEGORY_OPENABLE
        );

        intent.setType("audio/*");


        startActivityForResult(
                intent,
                REQUEST_PICK_AUDIO
        );
    }

    @Override
    protected void onActivityResult(
            int requestCode,
            int resultCode,
            Intent data
    ) {

        super.onActivityResult(
                requestCode,
                resultCode,
                data
        );


        if (requestCode ==
                REQUEST_PICK_AUDIO

                && resultCode ==
                RESULT_OK

                && data != null) {


            Uri uri =
                    data.getData();


            if (uri == null) {

                return;
            }


            selectedAudioUri =
                    uri;


            selectedFileName =
                    getDisplayName(uri);


            tvSelectedFile.setText(
                    selectedFileName
            );


            btnSeparate.setEnabled(
                    true
            );


            tvStatus.setText(
                    "Audio selected. Ready to upload."
            );
        }
    }

    private String getDisplayName(
            Uri uri
    ) {

        String name = null;

        Cursor cursor = null;


        try {

            cursor =
                    getContentResolver()
                            .query(
                                    uri,
                                    new String[]{
                                            OpenableColumns.DISPLAY_NAME
                                    },
                                    null,
                                    null,
                                    null
                            );


            if (cursor != null
                    && cursor.moveToFirst()) {


                int index =
                        cursor.getColumnIndex(
                                OpenableColumns.DISPLAY_NAME
                        );


                if (index >= 0) {

                    name =
                            cursor.getString(
                                    index
                            );
                }
            }

        } finally {

            if (cursor != null) {

                cursor.close();
            }
        }


        if (name == null
                || name.trim().isEmpty()) {

            return "song.wav";
        }


        return name;
    }


    // ============================
    // UPLOAD
    // ============================

    private void uploadAndSeparate() {

        if (selectedAudioUri == null) {

            toast(
                    "Choose an audio file first."
            );

            return;
        }


        resetPreviousResult();


        setLoading(
                true,
                "Preparing audio file..."
        );


        new Thread(() -> {

            try {

                File uploadFile =
                        copySelectedUriToCache(
                                selectedAudioUri,
                                selectedFileName
                        );


                runOnUiThread(() ->

                        setLoading(
                                true,
                                "Uploading song to server..."
                        )
                );


                callSeparationApi(
                        uploadFile
                );


            } catch (Exception e) {

                showError(
                        "Cannot prepare selected file: "
                                + e.getMessage()
                );
            }

        }).start();
    }


    private File copySelectedUriToCache(
            Uri uri,
            String displayName
    ) throws IOException {


        File uploadDir =
                new File(
                        getCacheDir(),
                        "uploads"
                );


        if (!uploadDir.exists()
                && !uploadDir.mkdirs()) {

            throw new IOException(
                    "Cannot create upload cache folder"
            );
        }


        String extension =
                ".wav";


        int dot =
                displayName.lastIndexOf('.');


        if (dot >= 0
                && dot < displayName.length() - 1) {

            extension =
                    displayName.substring(
                            dot
                    );
        }


        File outFile =
                File.createTempFile(
                        "input_",
                        extension,
                        uploadDir
                );


        try (
                InputStream input =
                        getContentResolver()
                                .openInputStream(uri);

                OutputStream output =
                        new FileOutputStream(
                                outFile
                        )
        ) {


            if (input == null) {

                throw new IOException(
                        "Cannot open selected audio file"
                );
            }


            byte[] buffer =
                    new byte[64 * 1024];


            int read;


            while (
                    (read =
                            input.read(buffer))
                            != -1
            ) {

                output.write(
                        buffer,
                        0,
                        read
                );
            }


            output.flush();
        }


        return outFile;
    }


    // ============================
    // API
    // ============================

    private void callSeparationApi(
            File uploadFile
    ) {


        String mimeType =
                getContentResolver()
                        .getType(
                                selectedAudioUri
                        );


        if (mimeType == null
                || mimeType
                .trim()
                .isEmpty()) {

            mimeType =
                    "audio/*";
        }


        MediaType mediaType =
                MediaType.parse(
                        mimeType
                );


        RequestBody fileBody =
                RequestBody.create(
                        uploadFile,
                        mediaType
                );


        MultipartBody multipartBody =
                new MultipartBody.Builder()

                        .setType(
                                MultipartBody.FORM
                        )

                        .addFormDataPart(
                                "file",
                                selectedFileName,
                                fileBody
                        )

                        .build();


        Request request =
                new Request.Builder()

                        .url(
                                SEPARATE_ENDPOINT
                        )

                        .post(
                                multipartBody
                        )

                        .build();


        httpClient
                .newCall(request)
                .enqueue(
                        new Callback() {

                            @Override
                            public void onFailure(
                                    Call call,
                                    IOException e
                            ) {

                                showError(
                                        "Upload failed: "
                                                + e.getMessage()
                                );
                            }


                            @Override
                            public void onResponse(
                                    Call call,
                                    Response response
                            ) throws IOException {


                                try (
                                        ResponseBody responseBody =
                                                response.body()
                                ) {


                                    if (!response.isSuccessful()) {

                                        String errorText =
                                                responseBody != null
                                                        ? responseBody.string()
                                                        : "";


                                        showError(
                                                "Server error "
                                                        + response.code()
                                                        + ": "
                                                        + errorText
                                        );

                                        return;
                                    }


                                    if (responseBody == null) {

                                        showError(
                                                "Server returned an empty response."
                                        );

                                        return;
                                    }


                                    String json =
                                            responseBody.string();


                                    runOnUiThread(() -> parseSeparationResponse(json));
                                }
                            }
                        }
                );
    }


    // ============================
    // JSON RESPONSE
    // ============================

    private void pollJobStatus(String jobId) {
        if (isDestroyed() || !jobId.equals(activeJobId)) return;
        Request request = new Request.Builder()
                .url(SERVER_BASE_URL + "/status/" + Uri.encode(jobId))
                .build();
        httpClient.newCall(request).enqueue(new Callback() {
            @Override
            public void onFailure(Call call, IOException e) {
                runOnUiThread(() -> {
                    if (isDestroyed() || !jobId.equals(activeJobId)) return;
                    activeJobId = null;
                    showError("Cannot check separation status: " + e.getMessage());
                });
            }

            @Override
            public void onResponse(Call call, Response response) throws IOException {
                try (ResponseBody body = response.body()) {
                    String json = body == null ? "" : body.string();
                    runOnUiThread(() -> {
                        if (isDestroyed() || !jobId.equals(activeJobId)) return;
                        if (!response.isSuccessful()) {
                            activeJobId = null;
                            showError("Status error " + response.code() + ": " + json);
                            return;
                        }
                        parseSeparationResponse(json);
                    });
                }
            }
        });
    }

    private void parseSeparationResponse(
            String json
    ) {

        try {

            if (isDestroyed()) return;

            JSONObject root =
                    new JSONObject(
                            json
                    );

            String status = root.optString("status", "");
            if ("pending".equals(status) || "processing".equals(status)) {
                String jobId = root.optString("job_id", activeJobId);
                if (jobId == null || jobId.isEmpty()) {
                    showError("Server returned no job_id.");
                    return;
                }
                activeJobId = jobId;
                setLoading(true, "pending".equals(status)
                        ? "Waiting for separation..." : "Separating audio. Please wait...");
                statusHandler.postDelayed(() -> pollJobStatus(jobId), 2000);
                return;
            }
            activeJobId = null;
            if ("failed".equals(status)) {
                showError("Separation failed: " + root.optString("error", "Unknown server error"));
                return;
            }
            if (!status.isEmpty() && !"done".equals(status)) {
                showError("Unknown separation status: " + status);
                return;
            }


            JSONObject container =
                    root.optJSONObject(
                            "result_urls"
                    );

            if (container == null) {
                container = root.optJSONObject("tracks");
            }


            if (container == null) {

                container =
                        root.optJSONObject(
                                "stems"
                        );
            }


            if (container == null) {

                container =
                        root.optJSONObject(
                                "files"
                        );
            }


            if (container == null) {

                container =
                        root;
            }


            vocals.url =
                    resolveTrackUrl(
                            root,
                            container,
                            "vocals"
                    );


            drums.url =
                    resolveTrackUrl(
                            root,
                            container,
                            "drums"
                    );


            bass.url =
                    resolveTrackUrl(
                            root,
                            container,
                            "bass"
                    );


            other.url =
                    resolveTrackUrl(
                            root,
                            container,
                            "other"
                    );


            for (TrackUI track : tracks) {

                if (track.url == null
                        || track.url.isEmpty()) {

                    showError(
                            "Missing URL for track: "
                                    + track.key
                                    + "\nResponse: "
                                    + json
                    );

                    return;
                }
            }


            runOnUiThread(() ->

                    setLoading(
                            true,
                            "Separation finished. Caching 4 tracks..."
                    )
            );


            cacheAllTracks();


        } catch (JSONException e) {

            showError(
                    "Invalid JSON returned by server: "
                            + e.getMessage()
                            + "\n"
                            + json
            );
        }
    }


    private String resolveTrackUrl(
            JSONObject root,
            JSONObject container,
            String key
    ) {


        String value =
                container.optString(
                        key,
                        ""
                );

        if (value.isEmpty()) {
            value = container.optString(key + ".wav", "");
        }


        if (value.isEmpty()) {

            value =
                    container.optString(
                            key + "_url",
                            ""
                    );
        }


        if (value.isEmpty()) {

            value =
                    root.optString(
                            key + "_url",
                            ""
                    );
        }


        if (value.isEmpty()) {

            value =
                    root.optString(
                            key,
                            ""
                    );
        }


        return makeAbsoluteUrl(
                value
        );
    }


    private String makeAbsoluteUrl(
            String value
    ) {

        if (value == null) {

            return "";
        }


        value =
                value.trim();


        if (value.isEmpty()) {

            return "";
        }


        if (
                value.startsWith(
                        "http://"
                )
                        ||
                        value.startsWith(
                                "https://"
                        )
        ) {

            Uri uri = Uri.parse(value);
            String host = uri.getHost();
            // Local backend links must use the server address reachable from Android.
            if ("localhost".equalsIgnoreCase(host) || "127.0.0.1".equals(host)
                    || "::1".equals(host) || "[::1]".equals(host)) {
                Uri server = Uri.parse(SERVER_BASE_URL);
                return uri.buildUpon().scheme(server.getScheme())
                        .encodedAuthority(server.getEncodedAuthority()).build().toString();
            }
            return value;
        }


        if (!value.startsWith("/")) {

            value =
                    "/" + value;
        }


        return SERVER_BASE_URL
                + value;
    }


    // ============================
    // CACHE 4 TRACK
    // ============================

    private void cacheAllTracks() {


        AtomicInteger remaining =
                new AtomicInteger(
                        tracks.length
                );


        AtomicInteger succeeded =
                new AtomicInteger(0);


        for (TrackUI track : tracks) {


            cacheOneTrack(
                    track,
                    success -> {


                        if (success) {

                            succeeded
                                    .incrementAndGet();
                        }


                        int left =
                                remaining
                                        .decrementAndGet();


                        runOnUiThread(() -> {


                            if (success) {

                                track.playButton
                                        .setEnabled(
                                                true
                                        );

                                track.downloadButton
                                        .setEnabled(
                                                true
                                        );
                            }


                            tvStatus.setText(
                                    String.format(
                                            Locale.US,

                                            "Caching stems... %d/%d ready",

                                            tracks.length - left,

                                            tracks.length
                                    )
                            );


                            if (left == 0) {

                                btnChooseFile.setEnabled(true);

                                progressBar.setVisibility(
                                        View.GONE
                                );


                                btnSeparate.setEnabled(
                                        true
                                );


                                boolean allReady =
                                        succeeded.get()
                                                ==
                                                tracks.length;


                                btnPlayAll.setEnabled(
                                        allReady
                                );


                                btnStopAll.setEnabled(
                                        allReady
                                );


                                if (allReady) {

                                    tvStatus.setText(
                                            "4 tracks ready. You can play, mix volume, or download."
                                    );

                                } else {

                                    tvStatus.setText(
                                            "Some tracks could not be cached. Check server URLs/network."
                                    );
                                }
                            }
                        });
                    }
            );
        }
    }


    private void cacheOneTrack(
            TrackUI track,
            CacheCallback callback
    ) {


        File cacheDir =
                new File(
                        getCacheDir(),
                        "separated_stems"
                );


        if (!cacheDir.exists()
                && !cacheDir.mkdirs()) {

            callback.onDone(false);

            return;
        }


        String urlHash =
                Integer.toHexString(
                        track.url.hashCode()
                );


        File outputFile =
                new File(
                        cacheDir,
                        track.key
                                + "_"
                                + urlHash
                                + ".wav"
                );


        if (
                outputFile.exists()
                        &&
                        outputFile.length() > 0
        ) {

            track.cacheFile =
                    outputFile;


            callback.onDone(
                    true
            );

            return;
        }


        File tempFile =
                new File(
                        cacheDir,
                        track.key
                                + "_"
                                + urlHash
                                + ".part"
                );


        Request request =
                new Request.Builder()

                        .url(
                                track.url
                        )

                        .get()

                        .build();


        httpClient
                .newCall(request)
                .enqueue(
                        new Callback() {

                            @Override
                            public void onFailure(
                                    Call call,
                                    IOException e
                            ) {

                                callback.onDone(
                                        false
                                );
                            }


                            @Override
                            public void onResponse(
                                    Call call,
                                    Response response
                            ) throws IOException {


                                try (
                                        ResponseBody body =
                                                response.body()
                                ) {


                                    if (
                                            !response.isSuccessful()
                                                    ||
                                                    body == null
                                    ) {

                                        callback.onDone(
                                                false
                                        );

                                        return;
                                    }


                                    try (
                                            InputStream input =
                                                    body.byteStream();

                                            FileOutputStream output =
                                                    new FileOutputStream(
                                                            tempFile
                                                    )
                                    ) {


                                        byte[] buffer =
                                                new byte[
                                                        64 * 1024
                                                        ];


                                        int read;


                                        while (
                                                (read =
                                                        input.read(
                                                                buffer
                                                        ))
                                                        != -1
                                        ) {


                                            output.write(
                                                    buffer,
                                                    0,
                                                    read
                                            );
                                        }


                                        output.flush();
                                    }


                                    if (
                                            outputFile.exists()
                                    ) {

                                        outputFile.delete();
                                    }


                                    boolean renamed =
                                            tempFile.renameTo(
                                                    outputFile
                                            );


                                    if (!renamed) {

                                        copyFile(
                                                tempFile,
                                                outputFile
                                        );

                                        tempFile.delete();
                                    }


                                    track.cacheFile =
                                            outputFile;


                                    callback.onDone(

                                            outputFile.exists()
                                                    &&
                                                    outputFile.length()
                                                            >
                                                            0
                                    );


                                } catch (
                                        Exception e
                                ) {


                                    callback.onDone(
                                            false
                                    );
                                }
                            }
                        }
                );
    }


    private void copyFile(
            File source,
            File target
    ) throws IOException {


        try (
                InputStream input =
                        new java.io.FileInputStream(
                                source
                        );

                OutputStream output =
                        new FileOutputStream(
                                target
                        )
        ) {


            byte[] buffer =
                    new byte[
                            64 * 1024
                            ];


            int read;


            while (
                    (read =
                            input.read(
                                    buffer
                            ))
                            != -1
            ) {


                output.write(
                        buffer,
                        0,
                        read
                );
            }


            output.flush();
        }
    }


    // ============================
    // PLAYER
    // ============================

    private void toggleTrack(
            TrackUI track
    ) {


        if (
                track.cacheFile == null
                        ||
                        !track.cacheFile.exists()
        ) {


            toast(
                    track.title
                            + " is not cached yet."
            );

            return;
        }


        if (
                track.player != null
                        &&
                        track.player.isPlaying()
        ) {


            track.player.pause();


            track.playButton.setText(
                    "Play"
            );


            return;
        }


        if (track.player != null) {


            track.player.start();


            track.playButton.setText(
                    "Pause"
            );


            return;
        }


        prepareAndPlay(
                track,
                0
        );
    }


    private void prepareAndPlay(
            TrackUI track,
            int seekToMs
    ) {


        releasePlayer(
                track
        );


        MediaPlayer player =
                new MediaPlayer();


        track.player =
                player;


        track.playButton.setText(
                "Loading..."
        );


        track.playButton.setEnabled(
                false
        );


        try {


            player.setDataSource(
                    track.cacheFile
                            .getAbsolutePath()
            );


            player.setVolume(
                    track.volume,
                    track.volume
            );


            player.setOnPreparedListener(
                    mp -> {


                        if (seekToMs > 0) {

                            mp.seekTo(
                                    seekToMs
                            );
                        }


                        mp.start();


                        track.playButton
                                .setEnabled(
                                        true
                                );


                        track.playButton
                                .setText(
                                        "Pause"
                                );
                    }
            );


            player.setOnCompletionListener(
                    mp -> {


                        track.playButton
                                .setText(
                                        "Play"
                                );


                        mp.seekTo(0);
                    }
            );


            player.setOnErrorListener(
                    (mp, what, extra) -> {


                        track.playButton
                                .setEnabled(
                                        true
                                );


                        track.playButton
                                .setText(
                                        "Play"
                                );


                        toast(
                                "Playback error: "
                                        + track.title
                        );


                        return true;
                    }
            );


            player.prepareAsync();


        } catch (IOException e) {


            track.playButton
                    .setEnabled(
                            true
                    );


            track.playButton
                    .setText(
                            "Play"
                    );


            releasePlayer(
                    track
            );


            toast(
                    "Cannot play "
                            + track.title
                            + ": "
                            + e.getMessage()
            );
        }
    }


    // ============================
    // MIXING
    // ============================

    private void playAllTracks() {


        for (
                TrackUI track
                :
                tracks
        ) {


            if (
                    track.cacheFile == null
                            ||
                            !track.cacheFile.exists()
            ) {


                toast(
                        "All 4 tracks must be cached first."
                );


                return;
            }
        }


        for (
                TrackUI track
                :
                tracks
        ) {


            prepareAndPlay(
                    track,
                    0
            );
        }


        tvStatus.setText(
                "Playing 4 stems. Move each slider to mix volume."
        );
    }


    private void stopAllTracks() {


        for (
                TrackUI track
                :
                tracks
        ) {


            if (track.player != null) {


                try {


                    track.player.pause();


                    track.player.seekTo(
                            0
                    );


                    track.playButton
                            .setText(
                                    "Play"
                            );


                } catch (
                        IllegalStateException ignored
                ) {

                }
            }
        }


        tvStatus.setText(
                "Playback stopped."
        );
    }


    // ============================
    // DOWNLOAD MANAGER
    // ============================

    private void downloadTrack(
            TrackUI track
    ) {


        if (
                track.url == null
                        ||
                        track.url.isEmpty()
        ) {


            toast(
                    "No download URL for "
                            + track.title
            );


            return;
        }


        if (
                Build.VERSION.SDK_INT
                        <= Build.VERSION_CODES.P

                        &&

                        checkSelfPermission(
                                Manifest.permission
                                        .WRITE_EXTERNAL_STORAGE
                        )

                                !=
                                PackageManager
                                        .PERMISSION_GRANTED
        ) {


            requestPermissions(
                    new String[]{
                            Manifest.permission
                                    .WRITE_EXTERNAL_STORAGE
                    },

                    REQUEST_WRITE_STORAGE
            );


            toast(
                    "Allow storage permission, then tap Download again."
            );


            return;
        }


        String fileName =
                buildDownloadFileName(
                        track.key
                );


        Uri uri =
                Uri.parse(
                        track.url
                );


        DownloadManager.Request request =
                new DownloadManager.Request(
                        uri
                )

                        .setTitle(
                                fileName
                        )

                        .setDescription(
                                "Downloading separated "
                                        + track.title
                                        + " track"
                        )

                        .setMimeType(
                                "audio/wav"
                        )

                        .setNotificationVisibility(
                                DownloadManager.Request
                                        .VISIBILITY_VISIBLE_NOTIFY_COMPLETED
                        )

                        .setAllowedOverMetered(
                                true
                        )

                        .setAllowedOverRoaming(
                                false
                        )

                        .setDestinationInExternalPublicDir(
                                Environment
                                        .DIRECTORY_DOWNLOADS,

                                "MusicSeparator/"
                                        + fileName
                        );


        DownloadManager manager =
                (DownloadManager)
                        getSystemService(
                                Context.DOWNLOAD_SERVICE
                        );


        if (manager == null) {


            toast(
                    "DownloadManager is not available."
            );


            return;
        }


        long id =
                manager.enqueue(
                        request
                );


        toast(
                "Download started: "
                        + track.title
                        + " (#"
                        + id
                        + ")"
        );
    }


    private String buildDownloadFileName(
            String stem
    ) {


        String base =
                selectedFileName;


        int dot =
                base.lastIndexOf('.');


        if (dot > 0) {

            base =
                    base.substring(
                            0,
                            dot
                    );
        }


        base =
                base.replaceAll(
                        "[^a-zA-Z0-9._-]",
                        "_"
                );


        return base
                + "_"
                + stem
                + ".wav";
    }


    // ============================
    // RESET
    // ============================

    private void resetPreviousResult() {


        btnPlayAll.setEnabled(
                false
        );


        btnStopAll.setEnabled(
                false
        );


        for (
                TrackUI track
                :
                tracks
        ) {


            releasePlayer(
                    track
            );


            track.url =
                    null;


            track.cacheFile =
                    null;


            track.playButton
                    .setEnabled(
                            false
                    );


            track.playButton
                    .setText(
                            "Play"
                    );


            track.downloadButton
                    .setEnabled(
                            false
                    );
        }
    }


    private void releasePlayer(
            TrackUI track
    ) {


        if (track.player != null) {


            try {

                track.player.stop();

            } catch (
                    Exception ignored
            ) {

            }


            try {

                track.player.release();

            } catch (
                    Exception ignored
            ) {

            }


            track.player =
                    null;
        }
    }


    // ============================
    // UI UTIL
    // ============================

    private void setLoading(
            boolean loading,
            String message
    ) {

        btnChooseFile.setEnabled(!loading);


        progressBar.setVisibility(
                loading
                        ?
                        View.VISIBLE
                        :
                        View.GONE
        );


        btnSeparate.setEnabled(
                !loading
                        &&
                        selectedAudioUri != null
        );


        tvStatus.setText(
                message
        );
    }


    private void showError(
            String message
    ) {


        runOnUiThread(() -> {


            progressBar.setVisibility(
                    View.GONE
            );

            btnChooseFile.setEnabled(true);


            btnSeparate.setEnabled(
                    selectedAudioUri != null
            );


            tvStatus.setText(
                    message
            );


            Toast.makeText(
                    MainActivity.this,
                    message,
                    Toast.LENGTH_LONG
            ).show();
        });
    }


    private void toast(
            String message
    ) {


        runOnUiThread(() ->


                Toast.makeText(
                        MainActivity.this,
                        message,
                        Toast.LENGTH_SHORT
                ).show()
        );
    }


    // ============================
    // STORAGE PERMISSION
    // ============================

    private void requestLegacyStoragePermissionIfNeeded() {


        if (
                Build.VERSION.SDK_INT
                        <= Build.VERSION_CODES.P

                        &&

                        checkSelfPermission(
                                Manifest.permission
                                        .WRITE_EXTERNAL_STORAGE
                        )

                                !=

                                PackageManager
                                        .PERMISSION_GRANTED
        ) {


            requestPermissions(
                    new String[]{
                            Manifest.permission
                                    .WRITE_EXTERNAL_STORAGE
                    },

                    REQUEST_WRITE_STORAGE
            );
        }
    }


    // ============================
    // DESTROY
    // ============================

    @Override
    protected void onDestroy() {


        super.onDestroy();

        activeJobId = null;
        statusHandler.removeCallbacksAndMessages(null);


        for (
                TrackUI track
                :
                tracks
        ) {


            releasePlayer(
                    track
            );
        }
    }


    // ============================
    // CALLBACK
    // ============================

    private interface CacheCallback {

        void onDone(
                boolean success
        );
    }


    // ============================
    // TRACK OBJECT
    // ============================

    private static class TrackUI {


        final String key;

        final String title;

        final Button playButton;

        final Button downloadButton;

        final SeekBar volumeSeekBar;


        String url;

        File cacheFile;

        MediaPlayer player;

        float volume = 1f;


        TrackUI(
                String key,
                String title,
                Button playButton,
                Button downloadButton,
                SeekBar volumeSeekBar
        ) {


            this.key =
                    key;


            this.title =
                    title;


            this.playButton =
                    playButton;


            this.downloadButton =
                    downloadButton;


            this.volumeSeekBar =
                    volumeSeekBar;
        }
    }
}
