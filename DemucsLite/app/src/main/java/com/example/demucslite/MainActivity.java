package com.example.demucslite;

import android.content.ContentValues;
import android.content.Intent;
import android.content.res.ColorStateList;
import android.database.Cursor;
import android.media.AudioAttributes;
import android.media.AudioFocusRequest;
import android.media.AudioManager;
import android.media.MediaPlayer;
import android.net.Uri;
import android.os.Bundle;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.provider.MediaStore;
import android.provider.OpenableColumns;
import android.text.InputType;
import android.view.View;
import android.widget.EditText;
import android.widget.ImageButton;
import android.widget.ImageView;
import android.widget.SeekBar;
import android.widget.TextView;
import android.widget.Toast;

import androidx.activity.OnBackPressedCallback;
import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.appcompat.app.AlertDialog;
import androidx.appcompat.app.AppCompatActivity;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.lifecycle.ViewModelProvider;

import com.example.demucslite.ui.ProgressOrbitView;
import com.example.demucslite.ui.WaveformView;

import java.io.FileInputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.util.ArrayList;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends AppCompatActivity {
    private enum Screen { HOME, UPLOAD, PROCESSING, MIXER }
    private StudioSession session;
    private Screen currentScreen;
    private final Handler ui = new Handler(Looper.getMainLooper());
    private final ExecutorService exportWorker = Executors.newSingleThreadExecutor();
    private StudioSession.Stem[] boundStems;
    private final MediaPlayer[] players = new MediaPlayer[4];
    private final boolean[] prepared = new boolean[4];
    private final View[] cards = new View[4];
    private final int[] colors = {0xFFB5A0FF,0xFFCDF5A2,0xFFFFBD9A,0xFF91CDFF};
    private boolean playing, seeking, exporting;
    private int duration, playerGeneration;
    private AudioManager audioManager;
    private AudioFocusRequest focusRequest;
    private final ActivityResultLauncher<String[]> picker = registerForActivityResult(
            new ActivityResultContracts.OpenDocument(), this::onAudioChosen);
    private final Runnable tick = new Runnable() {
        @Override public void run() {
            if(playing && prepared[0] && players[0]!=null) {
                session.playbackPosition=players[0].getCurrentPosition();
                if(!seeking) {
                    ((SeekBar)findViewById(R.id.playbackSeek)).setProgress(session.playbackPosition);
                    updateTime();
                }
                ui.postDelayed(this,120);
            }
        }
    };

    @Override protected void onCreate(Bundle state) {
        super.onCreate(state);
        WindowCompat.setDecorFitsSystemWindows(getWindow(),false);
        setContentView(R.layout.activity_main);
        WindowCompat.getInsetsController(getWindow(),getWindow().getDecorView()).setAppearanceLightStatusBars(false);
        WindowCompat.getInsetsController(getWindow(),getWindow().getDecorView()).setAppearanceLightNavigationBars(false);
        ViewCompat.setOnApplyWindowInsetsListener(findViewById(R.id.appRoot),(v,insets)-> {
            androidx.core.graphics.Insets bars=insets.getInsets(WindowInsetsCompat.Type.systemBars()|WindowInsetsCompat.Type.displayCutout());
            v.setPadding(bars.left,bars.top,bars.right,bars.bottom);return insets;
        });
        session=new ViewModelProvider(this).get(StudioSession.class);
        audioManager=(AudioManager)getSystemService(AUDIO_SERVICE);
        focusRequest=new AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN)
                .setAudioAttributes(new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA)
                        .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC).build())
                .setOnAudioFocusChangeListener(change -> { if(change!=AudioManager.AUDIOFOCUS_GAIN) pause(); }).build();
        bindActions();
        Screen initial=Screen.HOME;
        if(state!=null) {
            try { initial=Screen.valueOf(state.getString("screen","HOME")); } catch(IllegalArgumentException ignored) { }
            if(session.selectedUri==null && state.getString("uri")!=null)
                session.select(Uri.parse(state.getString("uri")),state.getString("name","song.wav"),state.getLong("size",-1));
            if(initial==Screen.PROCESSING && !session.isBusy()) initial=session.stems!=null?Screen.MIXER:Screen.UPLOAD;
            if(initial==Screen.MIXER && session.stems==null) initial=Screen.UPLOAD;
        }
        display(initial,false);
        session.changes.observe(this,this::render);
        getOnBackPressedDispatcher().addCallback(this,new OnBackPressedCallback(true) {
            @Override public void handleOnBackPressed() {
                if(currentScreen==Screen.PROCESSING) confirmCancel();
                else if(currentScreen==Screen.HOME) { setEnabled(false);getOnBackPressedDispatcher().onBackPressed();setEnabled(true); }
                else { pause();display(Screen.HOME,true); }
            }
        });
    }

    private void bindActions() {
        findViewById(R.id.btnStart).setOnClickListener(v -> openUpload());
        findViewById(R.id.btnDemo).setOnClickListener(v -> startJob(true));
        findViewById(R.id.uploadZone).setOnClickListener(v -> picker.launch(new String[]{"audio/*"}));
        findViewById(R.id.btnRemoveFile).setOnClickListener(v -> session.select(null,"",-1));
        findViewById(R.id.btnSeparate).setOnClickListener(v -> startJob(false));
        findViewById(R.id.btnSettings).setOnClickListener(v -> showSettings());
        findViewById(R.id.btnBack).setOnClickListener(v -> getOnBackPressedDispatcher().onBackPressed());
        findViewById(R.id.btnCancel).setOnClickListener(v -> confirmCancel());
        findViewById(R.id.navHome).setOnClickListener(v -> { pause();display(Screen.HOME,true); });
        findViewById(R.id.navStudio).setOnClickListener(v -> {
            if(session.stems!=null) display(Screen.MIXER,true);else openUpload();
        });
        findViewById(R.id.btnPlayAll).setOnClickListener(v -> { if(playing) pause();else play(); });
        findViewById(R.id.btnResetMix).setOnClickListener(v -> {
            if(boundStems==null) return;
            for(int i=0;i<4;i++) {
                StudioSession.Stem stem=boundStems[i];stem.volume=100;stem.muted=false;stem.solo=false;
                ((SeekBar)cards[i].findViewById(R.id.stemVolume)).setProgress(100);
            }
            applyMix();toast("Đã đặt lại âm lượng của 4 track.");
        });
        findViewById(R.id.btnNewSong).setOnClickListener(v -> openUpload());
        findViewById(R.id.btnExport).setOnClickListener(v -> exportTracks(-1));
        ((SeekBar)findViewById(R.id.playbackSeek)).setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            @Override public void onProgressChanged(SeekBar bar,int value,boolean user) {
                if(user) { session.playbackPosition=value;updateTime(); }
            }
            @Override public void onStartTrackingTouch(SeekBar bar) { seeking=true; }
            @Override public void onStopTrackingTouch(SeekBar bar) {
                seeking=false;session.playbackPosition=bar.getProgress();
                seekPlayers(session.playbackPosition);updateTime();
            }
        });
    }

    private void openUpload() { pause();session.clearError();display(Screen.UPLOAD,true); }
    private void startJob(boolean demo) {
        releasePlayers();boundStems=null;session.playbackPosition=0;session.start(demo);
    }
    private void onAudioChosen(Uri uri) {
        if(uri==null) return;
        try {
            getContentResolver().takePersistableUriPermission(uri,Intent.FLAG_GRANT_READ_URI_PERMISSION);
        } catch(SecurityException ignored) { }
        String name="song.wav";long size=-1;
        try(Cursor cursor=getContentResolver().query(uri,new String[]{OpenableColumns.DISPLAY_NAME,OpenableColumns.SIZE},null,null,null)) {
            if(cursor!=null && cursor.moveToFirst()) {
                int ni=cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME),si=cursor.getColumnIndex(OpenableColumns.SIZE);
                if(ni>=0&&!cursor.isNull(ni)) name=cursor.getString(ni);
                if(si>=0&&!cursor.isNull(si)) size=cursor.getLong(si);
            }
        } catch(Exception e) { toast("Không đọc được file. Hãy chọn lại.");return; }
        String lower=name.toLowerCase(Locale.ROOT);
        if(!(lower.endsWith(".mp3")||lower.endsWith(".wav")||lower.endsWith(".flac")||lower.endsWith(".m4a"))) {
            toast("Hỗ trợ MP3, WAV, FLAC và M4A.");return;
        }
        if(size>StudioSession.MAX_BYTES) { toast("Hãy chọn file không quá 50 MB.");return; }
        if(size==0) { toast("File này đang trống.");return; }
        session.select(uri,name,size);
        display(Screen.UPLOAD,true);
    }

    private void render(StudioSession state) {
        boolean selected=state.selectedUri!=null;
        findViewById(R.id.selectedFileCard).setVisibility(selected?View.VISIBLE:View.GONE);
        text(R.id.selectedFileName,state.fileName);
        String ext=state.fileName.contains(".")?state.fileName.substring(state.fileName.lastIndexOf('.')+1).toUpperCase(Locale.ROOT):"AUDIO";
        text(R.id.selectedFileMeta,ext+" · "+(state.fileSize<0?"Sẵn sàng":String.format(Locale.ROOT,"%.1f MB",state.fileSize/1048576.0)));
        text(R.id.uploadPrompt,selected?"Chọn một bài hát khác":"Chạm để chọn nhạc");
        findViewById(R.id.btnSeparate).setEnabled(selected&&!state.isBusy());
        findViewById(R.id.uploadError).setVisibility(state.error.isEmpty()?View.GONE:View.VISIBLE);
        text(R.id.uploadError,state.error);
        if(state.isBusy()) {
            display(Screen.PROCESSING,true);
            ((ProgressOrbitView)findViewById(R.id.progressOrbit)).setProgress(state.progress);
            text(R.id.processingFile,state.resultName);
            text(R.id.processingDescription,state.demo?"Đang tạo âm thanh để bạn thử bàn phối.":getString(R.string.processing_description));
            text(R.id.stepSubtitle0,state.demo?"Chuẩn bị âm thanh mẫu":"Đưa âm thanh vào studio");
            text(R.id.stepSubtitle1,state.demo?"Tạo trực tiếp, không cần máy chủ":"Nhận diện giọng hát và nhạc cụ");
            text(R.id.stepSubtitle2,state.demo?"Giai điệu, trống, bass và hợp âm":"Tải 4 track về thiết bị");
            text(R.id.processingStatus,state.message);
            text(R.id.progressValue,state.progress>=0?state.progress+"%":state.phase==StudioSession.Phase.SEPARATING?"AI":"•••");
            String label=state.demo?"TẠO DEMO":state.phase==StudioSession.Phase.UPLOADING?"TẢI NHẠC LÊN":
                    state.phase==StudioSession.Phase.SEPARATING?"ĐANG TÁCH ÂM":state.phase==StudioSession.Phase.CACHING?"TẢI KẾT QUẢ":
                            state.phase==StudioSession.Phase.QUEUED?"ĐANG CHỜ":"CHUẨN BỊ";
            text(R.id.progressLabel,label);
            text(R.id.processingHint,state.demo?"Bản demo được tạo trên thiết bị.\nĐây là âm thanh tổng hợp để thử bàn phối.":
                    "Giữ ứng dụng mở hoặc chạy nền khi chờ.\nThời gian xử lý tùy độ dài bài hát.");
            int step=state.demo?2:state.phase==StudioSession.Phase.CACHING?2:
                    state.phase==StudioSession.Phase.SEPARATING||state.phase==StudioSession.Phase.QUEUED?1:0;
            int[] numbers={R.id.stepNumber0,R.id.stepNumber1,R.id.stepNumber2};
            int[] titles={R.id.stepTitle0,R.id.stepTitle1,R.id.stepTitle2};
            int[] checks={R.id.stepCheck0,R.id.stepCheck1,R.id.stepCheck2};
            for(int i=0;i<3;i++) {
                TextView number=findViewById(numbers[i]);number.setText(i<step?"✓":"0"+(i+1));
                number.setTextColor(i<=step?colors[i==step?0:1]:getColor(R.color.muted));
                ((TextView)findViewById(titles[i])).setTextColor(getColor(i<=step?R.color.paper:R.color.muted));
                findViewById(checks[i]).setVisibility(i<step?View.VISIBLE:View.INVISIBLE);
            }
            text(R.id.stepTitle0,state.demo?"Demo trên thiết bị":"Tải nhạc lên");
            text(R.id.stepTitle1,state.demo?"Không sử dụng AI":"AI tách âm thanh");
            text(R.id.stepTitle2,state.demo?"Tạo 4 track tổng hợp":"Chuẩn bị bản phối");
        } else if(state.phase==StudioSession.Phase.ERROR) {
            display(Screen.UPLOAD,true);
            // Keep the inline failure visible even when a selected file makes the page taller.
            findViewById(R.id.uploadError).post(() -> {
                View error=findViewById(R.id.uploadError);
                error.requestRectangleOnScreen(new android.graphics.Rect(0,0,error.getWidth(),error.getHeight()),true);
            });
        }
        else if(state.phase==StudioSession.Phase.READY && state.stems!=boundStems) {
            boolean showResult=currentScreen==Screen.PROCESSING||currentScreen==Screen.MIXER;
            bindMixer();
            if(showResult) display(Screen.MIXER,true);
        }
    }

    private void display(Screen screen,boolean animate) {
        if(currentScreen==screen) return;
        if(screen==Screen.MIXER && session.stems==null) screen=Screen.UPLOAD;
        currentScreen=screen;
        int[] ids={R.id.screenHome,R.id.screenUpload,R.id.screenProcessing,R.id.screenMixer};
        for(int i=0;i<ids.length;i++) {
            View view=findViewById(ids[i]);view.animate().cancel();view.setVisibility(i==screen.ordinal()?View.VISIBLE:View.GONE);
            if(i==screen.ordinal() && animate) {
                view.setAlpha(0);view.setTranslationY(12*getResources().getDisplayMetrics().density);
                view.animate().alpha(1).translationY(0).setDuration(220).start();
            } else { view.setAlpha(1);view.setTranslationY(0); }
        }
        boolean home=screen==Screen.HOME;
        findViewById(R.id.btnBack).setVisibility(home?View.GONE:View.VISIBLE);
        findViewById(R.id.brandIcon).setVisibility(home?View.VISIBLE:View.GONE);
        findViewById(R.id.btnSettings).setVisibility(screen==Screen.PROCESSING?View.GONE:View.VISIBLE);
        findViewById(R.id.bottomNav).setVisibility(screen==Screen.PROCESSING?View.GONE:View.VISIBLE);
        text(R.id.toolbarTitle,home?"demucs lite":screen==Screen.UPLOAD?"Thêm bài hát":screen==Screen.PROCESSING?"Phòng tách âm":"Mix studio");
        TextView homeNav=findViewById(R.id.navHome),studioNav=findViewById(R.id.navStudio);
        homeNav.setTextColor(getColor(home?R.color.purple:R.color.muted));
        homeNav.setCompoundDrawableTintList(ColorStateList.valueOf(getColor(home?R.color.purple:R.color.muted)));
        studioNav.setTextColor(getColor(home?R.color.muted:R.color.purple));
        studioNav.setCompoundDrawableTintList(ColorStateList.valueOf(getColor(home?R.color.muted:R.color.purple)));
        ViewCompat.setAccessibilityPaneTitle(findViewById(ids[screen.ordinal()]),((TextView)findViewById(R.id.toolbarTitle)).getText());
    }

    private void bindMixer() {
        releasePlayers();boundStems=session.stems;
        text(R.id.mixerFileName,session.resultName);
        text(R.id.mixerMeta,session.demo?"DEMO · Âm thanh tổng hợp":"4 track · WAV không nén");
        text(R.id.resultBadge,session.demo?"DEMO / OFFLINE":"4 TRACK SẴN SÀNG");
        String[] names={"Vocals","Drums","Bass","Other"},descriptions={"Giọng hát","Trống & bộ gõ","Âm trầm","Nhạc cụ khác"};
        int[] roots={R.id.trackVocals,R.id.trackDrums,R.id.trackBass,R.id.trackOther};
        int[] icons={R.drawable.ic_mic,R.drawable.ic_drums,R.drawable.ic_bass,R.drawable.ic_music};
        for(int i=0;i<4;i++) {
            final int index=i;StudioSession.Stem stem=boundStems[i];View card=findViewById(roots[i]);cards[i]=card;
            ((TextView)card.findViewById(R.id.stemName)).setText(names[i]);
            ((TextView)card.findViewById(R.id.stemDescription)).setText(session.demo?new String[]{"Giai điệu tổng hợp","Trống điện tử","Bass tổng hợp","Hợp âm tổng hợp"}[i]:descriptions[i]);
            ImageView icon=card.findViewById(R.id.stemIcon);icon.setImageResource(icons[i]);icon.setImageTintList(ColorStateList.valueOf(colors[i]));
            ((WaveformView)card.findViewById(R.id.stemWave)).setWaveform(stem.envelope,colors[i]);
            SeekBar slider=card.findViewById(R.id.stemVolume);slider.setProgress(stem.volume);
            slider.setProgressTintList(ColorStateList.valueOf(colors[i]));slider.setThumbTintList(ColorStateList.valueOf(colors[i]));
            slider.setContentDescription("Âm lượng "+names[i]);
            ((TextView)card.findViewById(R.id.stemPercent)).setText(stem.volume+"%");
            slider.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
                @Override public void onProgressChanged(SeekBar bar,int value,boolean user) {
                    stem.volume=value;((TextView)card.findViewById(R.id.stemPercent)).setText(value+"%");applyMix();
                }
                @Override public void onStartTrackingTouch(SeekBar bar) { }
                @Override public void onStopTrackingTouch(SeekBar bar) { }
            });
            card.findViewById(R.id.stemMute).setContentDescription("Tắt âm "+names[i]);
            card.findViewById(R.id.stemMute).setOnClickListener(v -> { stem.muted=!stem.muted;applyMix(); });
            card.findViewById(R.id.stemSolo).setContentDescription("Nghe riêng "+names[i]);
            card.findViewById(R.id.stemSolo).setOnClickListener(v -> {
                boolean enable=!stem.solo;for(StudioSession.Stem s:boundStems) s.solo=false;
                stem.solo=enable;if(enable) stem.muted=false;applyMix();
            });
            card.findViewById(R.id.stemDownload).setContentDescription("Lưu "+names[i]+" WAV");
            card.findViewById(R.id.stemDownload).setOnClickListener(v -> exportTracks(index));
        }
        applyMix();preparePlayers();
    }

    private void preparePlayers() {
        findViewById(R.id.btnPlayAll).setEnabled(false);
        int token=++playerGeneration;
        for(int i=0;i<4;i++) {
            final int index=i;MediaPlayer player=new MediaPlayer();players[i]=player;
            player.setAudioAttributes(new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA).setContentType(AudioAttributes.CONTENT_TYPE_MUSIC).build());
            player.setOnPreparedListener(mp -> {
                if(token!=playerGeneration) return;
                prepared[index]=true;applyMix();
                for(boolean ready:prepared) if(!ready) return;
                duration=Integer.MAX_VALUE;for(MediaPlayer p:players) duration=Math.min(duration,p.getDuration());
                session.playbackPosition=Math.min(session.playbackPosition,duration);
                ((SeekBar)findViewById(R.id.playbackSeek)).setMax(duration);
                ((SeekBar)findViewById(R.id.playbackSeek)).setProgress(session.playbackPosition);
                seekPlayers(session.playbackPosition);updateTime();
                text(R.id.totalTime,time(duration));findViewById(R.id.btnPlayAll).setEnabled(true);
            });
            player.setOnCompletionListener(mp -> {
                if(token!=playerGeneration) return;
                pause();session.playbackPosition=0;seekPlayers(0);
                ((SeekBar)findViewById(R.id.playbackSeek)).setProgress(0);updateTime();
            });
            player.setOnErrorListener((mp,what,extra) -> {
                if(token==playerGeneration) {
                    pause();prepared[index]=false;findViewById(R.id.btnPlayAll).setEnabled(false);
                    toast("Không đọc được track "+boundStems[index].key+". Bạn vẫn có thể lưu file WAV.");
                }
                return true;
            });
            try { player.setDataSource(boundStems[i].file.getAbsolutePath());player.prepareAsync(); }
            catch(IOException e) { toast("Không mở được track "+boundStems[i].key); }
        }
    }
    private void applyMix() {
        if(boundStems==null) return;
        boolean solo=false;for(StudioSession.Stem stem:boundStems) solo|=stem.solo;
        for(int i=0;i<4;i++) {
            StudioSession.Stem stem=boundStems[i];boolean audible=!stem.muted&&(!solo||stem.solo);
            // Leave headroom for the sum of four independently played stems.
            float volume=audible?stem.volume/100f*.7f:0;
            if(prepared[i]&&players[i]!=null) players[i].setVolume(volume,volume);
            if(cards[i]==null) continue;
            ImageButton mute=cards[i].findViewById(R.id.stemMute);mute.setImageResource(stem.muted?R.drawable.ic_mute:R.drawable.ic_volume);
            mute.setImageTintList(ColorStateList.valueOf(stem.muted?colors[i]:getColor(R.color.muted)));
            ViewCompat.setStateDescription(mute,stem.muted?"Đã tắt âm":"Đang bật âm");
            TextView s=cards[i].findViewById(R.id.stemSolo);s.setTextColor(stem.solo?colors[i]:getColor(R.color.muted));
            ViewCompat.setStateDescription(s,stem.solo?"Đang nghe riêng":"Không nghe riêng");
            cards[i].findViewById(R.id.stemWave).setAlpha(audible?1:.3f);
        }
    }
    private void play() {
        for(boolean ready:prepared) if(!ready) { toast("Đang chuẩn bị âm thanh…");return; }
        if(audioManager.requestAudioFocus(focusRequest)!=AudioManager.AUDIOFOCUS_REQUEST_GRANTED) {
            toast("Chưa thể phát nhạc lúc này.");return;
        }
        for(MediaPlayer player:players) player.start();playing=true;
        ImageButton play=findViewById(R.id.btnPlayAll);play.setImageResource(R.drawable.ic_pause);play.setContentDescription("Tạm dừng bản phối");
        ui.removeCallbacks(tick);ui.post(tick);
    }
    private void pause() {
        if(playing&&players[0]!=null&&prepared[0]) session.playbackPosition=players[0].getCurrentPosition();
        for(int i=0;i<4;i++) if(prepared[i]&&players[i]!=null&&players[i].isPlaying()) players[i].pause();
        playing=false;ui.removeCallbacks(tick);
        ImageButton play=findViewById(R.id.btnPlayAll);
        if(play!=null) { play.setImageResource(R.drawable.ic_play);play.setContentDescription("Phát bản phối"); }
        if(audioManager!=null&&focusRequest!=null) audioManager.abandonAudioFocusRequest(focusRequest);
    }
    private void seekPlayers(int position) {
        for(int i=0;i<4;i++) if(prepared[i]&&players[i]!=null) players[i].seekTo(position,MediaPlayer.SEEK_CLOSEST);
    }
    private void releasePlayers() {
        pause();playerGeneration++;
        for(int i=0;i<4;i++) { prepared[i]=false;if(players[i]!=null) { players[i].release();players[i]=null; } }
    }
    private void updateTime() {
        text(R.id.currentTime,time(session.playbackPosition));
        for(View card:cards) if(card!=null) ((WaveformView)card.findViewById(R.id.stemWave)).setPosition(duration>0?session.playbackPosition/(float)duration:0);
    }
    private String time(int ms) { return String.format(Locale.ROOT,"%d:%02d",ms/60000,(ms/1000)%60); }

    private void exportTracks(int only) {
        if(boundStems==null||exporting) return;
        exporting=true;findViewById(R.id.btnExport).setEnabled(false);text(R.id.btnExport,"Đang lưu WAV…");
        StudioSession.Stem[] results=boundStems;
        String name=session.resultName.replaceAll("\\.[^.]+$","").replaceAll("[^\\p{L}\\p{N}._-]","_");
        if(name.length()>70) name=name.substring(0,70);
        final String baseName=name;
        // Capture the application resolver so a rotation does not interrupt an export.
        android.content.ContentResolver resolver=getApplicationContext().getContentResolver();
        exportWorker.execute(() -> {
            ArrayList<Uri> created=new ArrayList<>();String failure=null;int count=0;
            try {
                for(int i=0;i<4;i++) {
                    if(only>=0&&only!=i) continue;
                    ContentValues values=new ContentValues();
                    values.put(MediaStore.Downloads.DISPLAY_NAME,baseName+"_"+results[i].key+".wav");
                    values.put(MediaStore.Downloads.MIME_TYPE,"audio/wav");
                    values.put(MediaStore.Downloads.RELATIVE_PATH,Environment.DIRECTORY_DOWNLOADS+"/DemucsLite");
                    values.put(MediaStore.Downloads.IS_PENDING,1);
                    Uri uri=resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI,values);
                    if(uri==null) throw new IOException("Không tạo được file trong Downloads.");
                    created.add(uri);
                    try(FileInputStream in=new FileInputStream(results[i].file);OutputStream out=resolver.openOutputStream(uri)) {
                        if(out==null) throw new IOException("Không mở được file để lưu.");
                        byte[] buffer=new byte[65536];int n;while((n=in.read(buffer))!=-1) out.write(buffer,0,n);
                    }
                }
                // Publish only after every requested WAV has been copied successfully.
                for(Uri uri:created) {
                    ContentValues done=new ContentValues();done.put(MediaStore.Downloads.IS_PENDING,0);
                    resolver.update(uri,done,null,null);count++;
                }
            } catch(Exception e) {
                failure="Không lưu được WAV. Kiểm tra dung lượng trống rồi thử lại.";
                for(Uri uri:created) { try { resolver.delete(uri,null,null); } catch(Exception ignored) { } }
            }
            final String error=failure;final int saved=count;
            ui.post(() -> {
                exporting=false;
                if(isDestroyed()) return;
                findViewById(R.id.btnExport).setEnabled(true);text(R.id.btnExport,"Lưu 4 track WAV     ↓");
                if(error!=null) { toast(error);return; }
                new AlertDialog.Builder(this).setTitle("Đã lưu "+saved+" track ✨")
                        .setMessage("File WAV nằm trong Downloads/DemucsLite.\n\nĐây là các track gốc đã tách; âm lượng slider chỉ áp dụng khi nghe trong ứng dụng.")
                        .setPositiveButton("Xong",(dialog,which)->{}).show();
            });
        });
    }

    private void showSettings() {
        EditText input=new EditText(this);input.setSingleLine();input.setText(session.serverUrl);
        input.setSelectAllOnFocus(true);input.setTextSize(14);
        input.setInputType(InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_URI);
        int padding=(int)(24*getResources().getDisplayMetrics().density);
        android.widget.LinearLayout box=new android.widget.LinearLayout(this);box.setPadding(padding,0,padding,0);box.addView(input,new android.widget.LinearLayout.LayoutParams(-1,Math.round(56*getResources().getDisplayMetrics().density)));
        AlertDialog dialog=new AlertDialog.Builder(this).setTitle("Kết nối máy chủ")
                .setMessage("Emulator: http://10.0.2.2:8000\nĐiện thoại: nhập IP LAN của máy chạy server.\nChỉ nhập địa chỉ gốc, không thêm /separate.")
                .setView(box).setNegativeButton("Đóng",null).setPositiveButton("Lưu",null).create();
        dialog.setOnShowListener(d -> dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(v -> {
            String value=input.getText().toString().trim().replaceAll("/+$","");Uri uri=Uri.parse(value);
            if(!("http".equals(uri.getScheme())||"https".equals(uri.getScheme()))||uri.getHost()==null
                    ||uri.getQuery()!=null||uri.getFragment()!=null||uri.getUserInfo()!=null
                    ||(uri.getPath()!=null&&!uri.getPath().isEmpty())) {
                input.setError("Nhập địa chỉ gốc hợp lệ, ví dụ http://10.0.2.2:8000");return;
            }
            session.setServer(value);dialog.dismiss();toast("Đã lưu địa chỉ máy chủ.");
        }));
        dialog.show();
    }
    private void confirmCancel() {
        if(!session.isBusy()) { display(Screen.UPLOAD,true);return; }
        new AlertDialog.Builder(this).setTitle("Dừng chờ xử lý?")
                .setMessage("Ứng dụng sẽ ngừng chờ và tải kết quả. Tác vụ đã gửi vẫn có thể tiếp tục trên máy chủ.")
                .setNegativeButton("Tiếp tục chờ",null).setPositiveButton("Dừng chờ",(d,w)-> { session.cancel();display(Screen.UPLOAD,true); }).show();
    }
    private void text(int id,String value) { ((TextView)findViewById(id)).setText(value); }
    private void toast(String value) { Toast.makeText(this,value,Toast.LENGTH_LONG).show(); }
    @Override protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);out.putString("screen",currentScreen.name());
        if(session.selectedUri!=null) { out.putString("uri",session.selectedUri.toString());out.putString("name",session.fileName);out.putLong("size",session.fileSize); }
    }
    @Override protected void onStop() { pause();super.onStop(); }
    @Override protected void onDestroy() {
        releasePlayers();ui.removeCallbacksAndMessages(null);exportWorker.shutdown();super.onDestroy();
    }
}
