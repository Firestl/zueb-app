'use strict';

const CONFIG = {
  maxBodyBytes: 65536,
  logCookies: true,
  logWebView: true,
  logSsl: true,
  logUrlConnection: true,
  ignoredDomains: ['umeng.com', 'gepush.com', 'getui.com']
};

function now() {
  return new Date().toISOString();
}

function safeToString(value) {
  try {
    if (value === null || value === undefined) {
      return null;
    }
    return value.toString();
  } catch (error) {
    return '[toString failed: ' + error + ']';
  }
}

function truncateText(text, limit) {
  if (text === null || text === undefined) {
    return null;
  }
  const stringValue = String(text);
  if (stringValue.length <= limit) {
    return stringValue;
  }
  return stringValue.slice(0, limit) + ' ...<truncated ' + (stringValue.length - limit) + ' chars>';
}

function emit(event, payload) {
  console.log(JSON.stringify({
    ts: now(),
    event: event,
    payload: payload || {}
  }));
}

function withJava(callback) {
  Java.perform(function () {
    try {
      callback();
    } catch (error) {
      emit('script_error', {
        error: safeToString(error),
        stack: safeToString(error && error.stack)
      });
    }
  });
}

function tryHook(name, callback) {
  try {
    callback();
    emit('hook_ready', { name: name });
  } catch (error) {
    emit('hook_skip', {
      name: name,
      error: safeToString(error)
    });
  }
}

function mapToObject(javaMap) {
  const result = {};
  try {
    if (!javaMap) {
      return result;
    }
    if (javaMap.keySet) {
      const keys = javaMap.keySet().toArray();
      for (let index = 0; index < keys.length; index++) {
        const key = keys[index];
        result[safeToString(key)] = safeToString(javaMap.get(key));
      }
      return result;
    }
    if (javaMap.entrySet) {
      const iterator = javaMap.entrySet().iterator();
      while (iterator.hasNext()) {
        const entry = iterator.next();
        result[safeToString(entry.getKey())] = safeToString(entry.getValue());
      }
    }
  } catch (error) {
    result.__error__ = safeToString(error);
  }
  return result;
}

function getHostFromUrl(value) {
  if (!value) {
    return null;
  }
  try {
    const match = String(value).match(/^[a-zA-Z][a-zA-Z0-9+.-]*:\/\/([^\/?#:]+)/);
    if (match && match[1]) {
      return match[1].toLowerCase();
    }
  } catch (error) {}
  return null;
}

function shouldIgnoreTarget(value) {
  if (!value) {
    return false;
  }
  const host = getHostFromUrl(value) || String(value).toLowerCase();
  return CONFIG.ignoredDomains.some(function (domain) {
    return host === domain || host.endsWith('.' + domain) || host.indexOf(domain) !== -1;
  });
}

function looksTextual(contentType) {
  if (!contentType) {
    return true;
  }
  const value = String(contentType).toLowerCase();
  return value.indexOf('text/') !== -1 ||
    value.indexOf('json') !== -1 ||
    value.indexOf('xml') !== -1 ||
    value.indexOf('x-www-form-urlencoded') !== -1 ||
    value.indexOf('javascript') !== -1 ||
    value.indexOf('html') !== -1 ||
    value.indexOf('plain') !== -1 ||
    value.indexOf('graphql') !== -1;
}

function hookSslBypass() {
  const X509TrustManager = Java.use('javax.net.ssl.X509TrustManager');
  const SSLContext = Java.use('javax.net.ssl.SSLContext');

  const PermissiveTrustManager = Java.registerClass({
    name: 'org.frida.zueb.PermissiveTrustManager',
    implements: [X509TrustManager],
    methods: {
      checkClientTrusted: function () {},
      checkServerTrusted: function () {},
      getAcceptedIssuers: function () {
        return [];
      }
    }
  });

  const trustManagers = [PermissiveTrustManager.$new()];
  const sslInit = SSLContext.init.overload('[Ljavax.net.ssl.KeyManager;', '[Ljavax.net.ssl.TrustManager;', 'java.security.SecureRandom');
  sslInit.implementation = function (keyManagers, originalTrustManagers, secureRandom) {
    emit('sslcontext_init', {
      replaced: true,
      originalTrustManagers: safeToString(originalTrustManagers)
    });
    return sslInit.call(this, keyManagers, trustManagers, secureRandom);
  };

  [
    'dc.squareup.okhttp3.CertificatePinner',
    'okhttp3.CertificatePinner',
    'com.squareup.okhttp.CertificatePinner'
  ].forEach(function (className) {
    tryHook(className, function () {
      const CertificatePinner = Java.use(className);
      CertificatePinner.check.overloads.forEach(function (overload) {
        overload.implementation = function () {
          const host = arguments.length > 0 ? safeToString(arguments[0]) : null;
          if (!shouldIgnoreTarget(host)) {
            emit('ssl_bypass', {
              type: className + '.check',
              host: host
            });
          }
          return;
        };
      });
    });
  });

  [
    'dc.squareup.okhttp3.internal.tls.OkHostnameVerifier',
    'okhttp3.internal.tls.OkHostnameVerifier',
    'com.squareup.okhttp.internal.tls.OkHostnameVerifier'
  ].forEach(function (className) {
    tryHook(className, function () {
      const Verifier = Java.use(className);
      Verifier.verify.overloads.forEach(function (overload) {
        overload.implementation = function () {
          const host = arguments.length > 0 ? safeToString(arguments[0]) : null;
          if (!shouldIgnoreTarget(host)) {
            emit('ssl_bypass', {
              type: className + '.verify',
              host: host
            });
          }
          return true;
        };
      });
    });
  });
}

function installOkHttp3Interceptor(okhttpPackage, okioPackage) {
  tryHook(okhttpPackage + '.OkHttpClient$Builder', function () {
    const Builder = Java.use(okhttpPackage + '.OkHttpClient$Builder');
    const Interceptor = Java.use(okhttpPackage + '.Interceptor');
    const Buffer = Java.use(okioPackage + '.Buffer');
    const interceptorClassName = 'org.frida.zueb.TraceInterceptor_' + okhttpPackage.replace(/\./g, '_');

    const TraceInterceptor = Java.registerClass({
      name: interceptorClassName,
      implements: [Interceptor],
      methods: {
        intercept: function (chain) {
          const request = chain.request();
          const requestUrl = safeToString(request.url());
          const skipTrace = shouldIgnoreTarget(requestUrl);
          const body = request.body();
          const headersText = truncateText(safeToString(request.headers()), 8192);
          let requestBodyText = null;
          let requestContentType = null;

          try {
            if (body) {
              requestContentType = safeToString(body.contentType());
              if (looksTextual(requestContentType)) {
                const buffer = Buffer.$new();
                body.writeTo(buffer);
                requestBodyText = truncateText(buffer.readUtf8(), CONFIG.maxBodyBytes);
              } else {
                requestBodyText = '[binary body omitted, content-type=' + requestContentType + ']';
              }
            }
          } catch (error) {
            requestBodyText = '[request body read failed: ' + safeToString(error) + ']';
          }

          if (!skipTrace) {
            emit('okhttp_request', {
              stack: okhttpPackage,
              method: safeToString(request.method()),
              url: requestUrl,
              headers: headersText,
              contentType: requestContentType,
              body: requestBodyText
            });
          }

          const response = chain.proceed(request);
          const responseUrl = safeToString(response.request().url());
          let responseBodyText = null;
          let responseContentType = null;

          try {
            const responseBody = response.body();
            if (responseBody) {
              responseContentType = safeToString(responseBody.contentType());
              if (looksTextual(responseContentType)) {
                const peeked = response.peekBody(CONFIG.maxBodyBytes);
                responseBodyText = truncateText(peeked.string(), CONFIG.maxBodyBytes);
              } else {
                responseBodyText = '[binary body omitted, content-type=' + responseContentType + ']';
              }
            }
          } catch (error) {
            responseBodyText = '[response body read failed: ' + safeToString(error) + ']';
          }

          if (!skipTrace && !shouldIgnoreTarget(responseUrl)) {
            emit('okhttp_response', {
              stack: okhttpPackage,
              code: response.code(),
              message: safeToString(response.message()),
              url: responseUrl,
              headers: truncateText(safeToString(response.headers()), 8192),
              contentType: responseContentType,
              body: responseBodyText
            });
          }

          return response;
        }
      }
    });

    const build = Builder.build.overload();
    build.implementation = function () {
      try {
        const interceptors = this.interceptors();
        let installed = false;
        for (let index = 0; index < interceptors.size(); index++) {
          const current = interceptors.get(index);
          if (safeToString(current.getClass().getName()) === interceptorClassName) {
            installed = true;
            break;
          }
        }
        if (!installed) {
          this.addInterceptor(TraceInterceptor.$new());
          emit('okhttp_hook', { stack: okhttpPackage, installed: true });
        }
      } catch (error) {
        emit('okhttp_hook', {
          stack: okhttpPackage,
          installed: false,
          error: safeToString(error)
        });
      }
      return build.call(this);
    };
  });
}

function hookUrlConnection() {
  const URL = Java.use('java.net.URL');

  const openConnection = URL.openConnection.overload();
  openConnection.implementation = function () {
    const result = openConnection.call(this);
    const url = safeToString(this.toString());
    if (!shouldIgnoreTarget(url)) {
      emit('urlconnection_open', {
        url: url,
        impl: safeToString(result.getClass().getName())
      });
    }
    return result;
  };

  const openConnectionProxy = URL.openConnection.overload('java.net.Proxy');
  openConnectionProxy.implementation = function (proxy) {
    const result = openConnectionProxy.call(this, proxy);
    const url = safeToString(this.toString());
    if (!shouldIgnoreTarget(url)) {
      emit('urlconnection_open', {
        url: url,
        proxy: safeToString(proxy),
        impl: safeToString(result.getClass().getName())
      });
    }
    return result;
  };

  tryHook('java.net.URLConnection.setRequestProperty', function () {
    const URLConnection = Java.use('java.net.URLConnection');
    const setRequestProperty = URLConnection.setRequestProperty.overload('java.lang.String', 'java.lang.String');
    setRequestProperty.implementation = function (key, value) {
      const url = safeToString(this.getURL());
      if (!shouldIgnoreTarget(url)) {
        emit('urlconnection_header', {
          url: url,
          key: safeToString(key),
          value: truncateText(safeToString(value), 2048)
        });
      }
      return setRequestProperty.call(this, key, value);
    };
  });
}

function hookWebView() {
  const WebView = Java.use('android.webkit.WebView');
  const JString = Java.use('java.lang.String');

  const loadUrl = WebView.loadUrl.overload('java.lang.String');
  loadUrl.implementation = function (url) {
    const targetUrl = safeToString(url);
    if (!shouldIgnoreTarget(targetUrl)) {
      emit('webview_load', {
        url: targetUrl,
        view: safeToString(this)
      });
    }
    return loadUrl.call(this, url);
  };

  const loadUrlWithHeaders = WebView.loadUrl.overload('java.lang.String', 'java.util.Map');
  loadUrlWithHeaders.implementation = function (url, headers) {
    const targetUrl = safeToString(url);
    if (!shouldIgnoreTarget(targetUrl)) {
      emit('webview_load', {
        url: targetUrl,
        headers: mapToObject(headers),
        view: safeToString(this)
      });
    }
    return loadUrlWithHeaders.call(this, url, headers);
  };

  const postUrl = WebView.postUrl.overload('java.lang.String', '[B');
  postUrl.implementation = function (url, postData) {
    const targetUrl = safeToString(url);
    if (!shouldIgnoreTarget(targetUrl)) {
      emit('webview_post', {
        url: targetUrl,
        bodyPreview: postData ? truncateText(safeToString(JString.$new(postData)), CONFIG.maxBodyBytes) : null,
        view: safeToString(this)
      });
    }
    return postUrl.call(this, url, postData);
  };

  const addJavascriptInterface = WebView.addJavascriptInterface.overload('java.lang.Object', 'java.lang.String');
  addJavascriptInterface.implementation = function (obj, name) {
    emit('webview_js_bridge', {
      interfaceName: safeToString(name),
      className: safeToString(obj ? obj.getClass().getName() : null)
    });
    return addJavascriptInterface.call(this, obj, name);
  };

  tryHook('android.webkit.SslErrorHandler.proceed', function () {
    const SslErrorHandler = Java.use('android.webkit.SslErrorHandler');
    const proceed = SslErrorHandler.proceed.overload();
    proceed.implementation = function () {
      emit('webview_ssl_proceed', {
        handler: safeToString(this)
      });
      return proceed.call(this);
    };
  });

  if (!CONFIG.logCookies) {
    return;
  }

  tryHook('android.webkit.CookieManager', function () {
    const CookieManager = Java.use('android.webkit.CookieManager');
    const setCookie = CookieManager.setCookie.overload('java.lang.String', 'java.lang.String');
    setCookie.implementation = function (url, value) {
      const cookieUrl = safeToString(url);
      if (!shouldIgnoreTarget(cookieUrl)) {
        emit('cookie_set', {
          url: cookieUrl,
          value: truncateText(safeToString(value), 4096)
        });
      }
      return setCookie.call(this, url, value);
    };

    try {
      const setCookieCb = CookieManager.setCookie.overload('java.lang.String', 'java.lang.String', 'android.webkit.ValueCallback');
      setCookieCb.implementation = function (url, value, callback) {
        const cookieUrl = safeToString(url);
        if (!shouldIgnoreTarget(cookieUrl)) {
          emit('cookie_set', {
            url: cookieUrl,
            value: truncateText(safeToString(value), 4096)
          });
        }
        return setCookieCb.call(this, url, value, callback);
      };
    } catch (error) {
      emit('hook_skip', {
        name: 'android.webkit.CookieManager.setCookie(3)',
        error: safeToString(error)
      });
    }
  });
}

setImmediate(function () {
  withJava(function () {
    emit('script_start', {
      package: 'com.supwisdom.zueb',
      maxBodyBytes: CONFIG.maxBodyBytes,
      ignoredDomains: CONFIG.ignoredDomains
    });

    if (CONFIG.logSsl) {
      hookSslBypass();
    }

    installOkHttp3Interceptor('dc.squareup.okhttp3', 'dc.squareup.okio');
    installOkHttp3Interceptor('okhttp3', 'okio');

    if (CONFIG.logWebView) {
      hookWebView();
    }

    if (CONFIG.logUrlConnection) {
      hookUrlConnection();
    }

    emit('script_ready', { package: 'com.supwisdom.zueb' });
  });
});
