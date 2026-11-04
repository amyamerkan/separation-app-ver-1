package com.example.demucslite;

import android.app.Application;
import android.net.Uri;
import android.os.Handler;
import android.os.Looper;

import androidx.annotation.NonNull;
import androidx.lifecycle.AndroidViewModel;
import androidx.lifecycle.MutableLiveData;

import com.example.demucslite.audio.DemoAudio;
import com.example.demucslite.audio.WavEnvelope;

import org.json.JSONObject;

import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import okhttp3.Call;
import okhttp3.MediaType;
import okhttp3.MultipartBody;
import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.RequestBody;
import okhttp3.Response;
import okhttp3.ResponseBody;
import okio.BufferedSink;

/** Owns the running job independently of the Activity, including across rotation. */
public class StudioSession extends AndroidViewModel {
    public enum Phase { IDLE, PREPARING, UPLOADING, QUEUED, SEPARATING, CACHING, READY, ERROR }
    public static final long MAX_BYTES = 50L * 1024 * 1024;
    public static final String[] KEYS = {"vocals", "drums", "bass", "other"};
    public final MutableLiveData<StudioSession> changes = new MutableLiveData<>();
    public Phase phase = Phase.IDLE;
    public Uri selectedUri;
    public String fileName = "", resultName = "", message = "", error = "";
    public long fileSize = -1;
    public int progress = -1;
    public int playbackPosition;
    public boolean demo;
    public Stem[] stems;
    public String serverUrl;
    private final Handler main = new Handler(Looper.getMainLooper());
    private final ExecutorService worker = Executors.newSingleThreadExecutor();
    private final AtomicInteger generation = new AtomicInteger();
    private volatile Call currentCall;
    private final OkHttpClient client = new OkHttpClient.Builder()
            .connectTimeout(15, TimeUnit.SECONDS).readTimeout(90, TimeUnit.SECONDS)
            .writeTimeout(120, TimeUnit.SECONDS).retryOnConnectionFailure(true).build();

    public StudioSession(@NonNull Application app) {
        super(app);
        serverUrl = app.getSharedPreferences("studio", 0)
                .getString("server", "http://10.0.2.2:8000");
        changes.setValue(this);
    }

    public static class Stem {
        public final String key;
        public final File file;
        public final float[] envelope;
        public int volume = 100;
        public boolean muted, solo;
        Stem(String key, File file) throws IOException {
            this.key=key; this.file=file; this.envelope=WavEnvelope.read(file, 128);
        }
    }

    public boolean isBusy() { return phase!=Phase.IDLE && phase!=Phase.READY && phase!=Phase.ERROR; }
    public void select(Uri uri, String name, long size) {
        selectedUri=uri;fileName=name;fileSize=size;error="";
        if(phase==Phase.ERROR) phase=Phase.IDLE;
        changes.setValue(this);
    }
    public void setServer(String value) {
        serverUrl=value;
        getApplication().getSharedPreferences("studio",0).edit().putString("server",value).apply();
    }
    public void clearError() { error=""; if(phase==Phase.ERROR) phase=Phase.IDLE; changes.setValue(this); }

    public void start(boolean useDemo) {
        if(isBusy()) return;
        if(!useDemo && selectedUri==null) return;
        int token=generation.incrementAndGet();
        demo=useDemo;stems=null;error="";progress=-1;phase=Phase.PREPARING;
        resultName=useDemo?"Neon nights · Demo":fileName;
        message=useDemo?"Đang tạo 4 track âm thanh tổng hợp trên thiết bị.":"Đang chuẩn bị file nhạc…";
        changes.setValue(this);
        final Uri source=selectedUri;
        final String name=fileName, base=serverUrl;
        worker.execute(() -> {
            File input=null;
            try {
                File folder=new File(getApplication().getCacheDir(),"studio_"+System.currentTimeMillis()+"_"+token);
                if(!folder.mkdirs()) throw new IOException("Không tạo được thư mục tạm.");
                if(useDemo) {
                    File[] files=DemoAudio.create(folder, percent -> update(token,Phase.CACHING,percent,
                            "Đang tạo bản demo · Âm thanh tổng hợp, không dùng AI."), () -> check(token));
                    Stem[] result=new Stem[4];
                    for(int i=0;i<4;i++) { check(token); result[i]=new Stem(KEYS[i],files[i]); }
                    // Briefly leave the completed state visible before opening the mixer.
                    main.postDelayed(() -> finish(token,result),650);
                    return;
                }
                String lower=name.toLowerCase(Locale.ROOT);
                if(!(lower.endsWith(".mp3")||lower.endsWith(".wav")||lower.endsWith(".flac")||lower.endsWith(".m4a")))
                    throw new IOException("Chọn file MP3, WAV, FLAC hoặc M4A nhé.");
                String suffix=name.substring(name.lastIndexOf('.'));
                input=new File(folder,"input"+suffix);
                try(InputStream in=getApplication().getContentResolver().openInputStream(source);
                    FileOutputStream out=new FileOutputStream(input)) {
                    if(in==null) throw new IOException("Không đọc được file đã chọn. Hãy chọn lại file.");
                    byte[] buffer=new byte[65536]; int n;long total=0;
                    while((n=in.read(buffer))!=-1) {
                        check(token);total+=n;
                        if(total>MAX_BYTES) throw new IOException("File vượt quá 50 MB. Hãy chọn file nhỏ hơn.");
                        out.write(buffer,0,n);
                    }
                    if(total==0) throw new IOException("File nhạc đang trống. Hãy chọn một file khác.");
                }
                check(token);
                final File upload=input;
                String type=getApplication().getContentResolver().getType(source);
                final MediaType mediaType=MediaType.parse(type==null?"application/octet-stream":type);
                RequestBody audio=new RequestBody() {
                    @Override public MediaType contentType() { return mediaType; }
                    @Override public long contentLength() { return upload.length(); }
                    @Override public void writeTo(@NonNull BufferedSink sink) throws IOException {
                        try(FileInputStream in=new FileInputStream(upload)) {
                            byte[] buffer=new byte[65536];int n,last=-1;long sent=0;
                            while((n=in.read(buffer))!=-1) {
                                check(token);sink.write(buffer,0,n);sent+=n;
                                int percent=(int)(sent*100/Math.max(1,upload.length()));
                                if(percent!=last) { last=percent;update(token,Phase.UPLOADING,percent,"Đang tải file nhạc lên máy chủ…"); }
                            }
                        }
                    }
                };
                update(token,Phase.UPLOADING,0,"Đang kết nối với máy chủ…");
                MultipartBody body=new MultipartBody.Builder().setType(MultipartBody.FORM)
                        .addFormDataPart("file",name,audio).build();
                JSONObject response=requestJson(token,new Request.Builder().url(base+"/separate").post(body).build());
                String jobId=response.optString("job_id","");
                long deadline=System.currentTimeMillis()+30*60*1000L;
                while(true) {
                    check(token);
                    String status=response.optString("status", "done");
                    if("failed".equals(status)) throw new IOException(response.optString("error","Máy chủ không thể tách bài hát này."));
                    if("done".equals(status)) break;
                    if(!"pending".equals(status) && !"processing".equals(status))
                        throw new IOException("Máy chủ trả về trạng thái chưa được hỗ trợ: "+status);
                    if(jobId.isEmpty()) throw new IOException("Máy chủ chưa trả về mã xử lý.");
                    update(token,"pending".equals(status)?Phase.QUEUED:Phase.SEPARATING,-1,
                            "pending".equals(status)?"Bài hát đang trong hàng đợi…":"AI đang tách 4 lớp âm thanh. Máy chủ chưa cung cấp phần trăm tiến trình.");
                    if(System.currentTimeMillis()>deadline) throw new IOException("Đã chờ hơn 30 phút. Kiểm tra máy chủ rồi thử lại.");
                    Thread.sleep(1800);
                    response=requestJson(token,new Request.Builder().url(base+"/status/"+Uri.encode(jobId)).build());
                }
                JSONObject urls=null;
                for(String key:new String[]{"result_urls","tracks","stems","files"}) {
                    urls=response.optJSONObject(key);if(urls!=null) break;
                }
                if(urls==null) urls=response;
                Stem[] result=new Stem[4];
                for(int i=0;i<4;i++) {
                    check(token);
                    String key=KEYS[i];
                    String value=urls.optString(key,urls.optString(key+".wav",urls.optString(key+"_url",response.optString(key+"_url",""))));
                    if(value.isEmpty() || "null".equals(value)) throw new IOException("Thiếu đường dẫn tải track "+key+".");
                    String url=absoluteUrl(base,value);
                    update(token,Phase.CACHING,i*25,"Đang tải track "+(i+1)+"/4 về thiết bị…");
                    File output=new File(folder,key+".wav");
                    Call call=client.newCall(new Request.Builder().url(url).build());currentCall=call;check(token);
                    try(Response http=call.execute()) {
                        ResponseBody data=http.body();
                        if(!http.isSuccessful()||data==null) throw new IOException("Không tải được track "+key+" (HTTP "+http.code()+").");
                        try(InputStream in=data.byteStream();FileOutputStream out=new FileOutputStream(output)) {
                            byte[] buffer=new byte[65536];int n;
                            while((n=in.read(buffer))!=-1) { check(token);out.write(buffer,0,n); }
                        }
                    }
                    result[i]=new Stem(key,output);
                    update(token,Phase.CACHING,(i+1)*25,"Đã sẵn sàng "+(i+1)+"/4 track.");
                }
                main.post(() -> finish(token,result));
            } catch(Exception e) {
                if(token==generation.get()) main.post(() -> {
                    if(token!=generation.get()) return;
                    phase=Phase.ERROR;progress=-1;
                    String detail=e.getMessage();
                    error=e instanceof java.net.ConnectException || e instanceof java.net.SocketTimeoutException
                            ?"Chưa kết nối được máy chủ. Kiểm tra địa chỉ trong Cài đặt hoặc thử bản demo."
                            :detail==null?"Có lỗi khi xử lý. Hãy thử lại.":detail;
                    changes.setValue(this);
                });
            } finally { if(input!=null) input.delete(); }
        });
    }
    private JSONObject requestJson(int token,Request request) throws Exception {
        check(token);Call call=client.newCall(request);currentCall=call;check(token);
        try(Response response=call.execute()) {
            ResponseBody body=response.body();String text=body==null?"":body.string();
            if(!response.isSuccessful()) {
                String detail="Máy chủ trả về lỗi HTTP "+response.code()+".";
                try { detail=new JSONObject(text).optString("detail",detail); } catch(Exception ignored) { }
                throw new IOException(detail);
            }
            if(text.isEmpty()) throw new IOException("Máy chủ trả về phản hồi trống.");
            return new JSONObject(text);
        }
    }
    static String absoluteUrl(String base,String value) {
        if(value.startsWith("http://")||value.startsWith("https://")) {
            Uri uri=Uri.parse(value);String host=uri.getHost();
            if("localhost".equalsIgnoreCase(host)||"127.0.0.1".equals(host)||"::1".equals(host)||"[::1]".equals(host)) {
                Uri server=Uri.parse(base);
                return uri.buildUpon().scheme(server.getScheme()).encodedAuthority(server.getEncodedAuthority()).build().toString();
            }
            return value;
        }
        return base+(value.startsWith("/")?"":"/")+value;
    }
    private void update(int token,Phase stage,int percent,String text) {
        main.post(() -> { if(token!=generation.get()) return;
            phase=stage;progress=percent;message=text;changes.setValue(this);
        });
    }
    private void finish(int token,Stem[] result) {
        if(token!=generation.get()) return;
        stems=result;phase=Phase.READY;progress=100;changes.setValue(this);
    }
    private void check(int token) throws IOException {
        if(token!=generation.get()||Thread.currentThread().isInterrupted()) throw new IOException("Đã dừng chờ.");
    }
    public void cancel() {
        generation.incrementAndGet();Call call=currentCall;if(call!=null) call.cancel();
        phase=Phase.IDLE;progress=-1;changes.setValue(this);
    }
    @Override protected void onCleared() {
        generation.incrementAndGet();Call call=currentCall;if(call!=null) call.cancel();
        worker.shutdownNow();client.dispatcher().cancelAll();
    }
}
