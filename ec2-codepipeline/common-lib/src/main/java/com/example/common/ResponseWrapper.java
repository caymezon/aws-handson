package com.example.common;

/**
 * API レスポンスを統一形式 {status, message, data} でラップするユーティリティクラス。
 * AWS CodeArtifact に publish され、Webアプリから依存として利用される。
 */
public class ResponseWrapper<T> {

    private final String status;
    private final String message;
    private final T data;

    private ResponseWrapper(String status, String message, T data) {
        this.status = status;
        this.message = message;
        this.data = data;
    }

    public static <T> ResponseWrapper<T> success(T data) {
        return new ResponseWrapper<>("ok", null, data);
    }

    public static <T> ResponseWrapper<T> error(String message) {
        return new ResponseWrapper<>("error", message, null);
    }

    public String getStatus()  { return status; }
    public String getMessage() { return message; }
    public T getData()         { return data; }
}
