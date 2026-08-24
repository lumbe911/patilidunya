@echo off
echo ========================================
echo   Patili Dünya - Veritabani Yedekleme
echo ========================================
echo.
echo Render Dashboard'dan DATABASE_URL kopyalayin
echo Ornek: postgres://user:pass@xxx.render.com:5432/patilidunya
echo.
set /p DB_URL="DATABASE_URL: "
echo.
echo Yedekleniyor...
pg_dump "%DB_URL%" > backup.sql
echo.
if %ERRORLEVEL% EQU 0 (
    echo BAŞARILI! backup.sql dosyası oluşturuldu.
    echo Bu dosyayı güvenli bir yere kopyalayın.
) else (
    echo HATA! pg_dump çalışmadı. PostgreSQL kurulu mu?
    echo https://www.postgresql.org/download/windows/ adresinden kurabilirsiniz.
)
echo.
pause
