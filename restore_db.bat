@echo off
echo ========================================
echo   Patili Dünya - Veritabani Geri Yukleme
echo ========================================
echo.
echo Yeni veritabani URL'sini girin
echo Ornek: postgres://user:pass@xxx.railway.app:5432/patilidunya
echo.
set /p NEW_DB_URL="Yeni DATABASE_URL: "
echo.
echo backup.sql dosyası bu klasörde mi?
echo.
set /p BACKUP_FILE="Backup dosya yolu (varsayılan: backup.sql): "
if "%BACKUP_FILE%"=="" set BACKUP_FILE=backup.sql
echo.
echo Geri yükleniyor... Bu işlem birkaç dakika sürebilir...
psql "%NEW_DB_URL%" < "%BACKUP_FILE%"
echo.
if %ERRORLEVEL% EQU 0 (
    echo BAŞARILI! Veritabanı geri yüklendi.
) else (
    echo HATA! psql çalışmadı. PostgreSQL kurulu mu?
    echo https://www.postgresql.org/download/windows/ adresinden kurabilirsiniz.
)
echo.
pause
