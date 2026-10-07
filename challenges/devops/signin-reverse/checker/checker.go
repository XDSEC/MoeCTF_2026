package main

import (
	"database/sql"
	"io"
	"log"
	"net/http"
	"os"
	"strings"
	"time"

	_ "github.com/go-sql-driver/mysql"
)

const (
	dbHost = "127.0.0.1:3306"
	dsn    = "moectf:xdsec@tcp(" + dbHost + ")/blog?charset=utf8mb4"
	webURL = "http://127.0.0.1:8080"
)

func getFlag() string {
	if flag := os.Getenv("FLAG"); flag != "" {
		return flag
	}
	if flag := os.Getenv("flag"); flag != "" {
		return flag
	}
	if flag := os.Getenv("Flag"); flag != "" {
		return flag
	}
	return "moectf{this-is-a-default-flag}"
}

func checkNginx() (bool, string) {
	client := http.Client{
		Timeout: 5 * time.Second,
	}

	resp, err := client.Get(webURL)
	if err != nil {
		return false, err.Error()
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return false, "HTTP status code: " + resp.Status
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return false, err.Error()
	}

	bodyStr := string(body)
	if strings.Contains(bodyStr, "Typecho") || strings.Contains(bodyStr, "<title>") {
		return true, ""
	}

	return false, "Response body does not contain Typecho or <title> tags"
}

func checkAboutPage() (bool, string) {
	client := http.Client{
		Timeout: 5 * time.Second,
	}

	aboutURL := webURL + "/index.php/start-page.html"
	resp, err := client.Get(aboutURL)
	if err != nil {
		return false, err.Error()
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return false, "HTTP status code: " + resp.Status
	}

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		return false, err.Error()
	}

	bodyStr := string(body)

	expectedText := "本页面由 Typecho 创建, 这只是个测试页面."
	if strings.Contains(bodyStr, expectedText) {
		return true, ""
	}

	if strings.Contains(bodyStr, "Typecho") && strings.Contains(bodyStr, "测试页面") {
		return true, "Found partial match"
	}

	return false, "Expected text not found in about page"
}

func flagExists(db *sql.DB, flagString string) bool {
	query := `SELECT COUNT(*) FROM typecho_contents WHERE text LIKE ?`
	var count int
	err := db.QueryRow(query, "%"+flagString+"%").Scan(&count)
	if err != nil {
		return false
	}
	return count > 0
}

func main() {
	flagString := getFlag()

	flagInjected := false

	for {
		time.Sleep(5 * time.Second)

		ok, _ := checkNginx()
		if !ok {
			continue
		}
		ok, _ = checkAboutPage()
		if !ok {
			continue
		}

		db, err := sql.Open("mysql", dsn)
		if err != nil {
			continue
		}

		if err := db.Ping(); err != nil {
			db.Close()
			continue
		}
		log.Printf("[+] 数据库连接成功")

		var tableCount int
		err = db.QueryRow("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'blog' AND table_name = 'typecho_contents'").Scan(&tableCount)
		if err != nil || tableCount == 0 {
			db.Close()
			continue
		}

		if !flagInjected {
			if flagExists(db, flagString) {
				flagInjected = true
				db.Close()
				continue
			}

			var cid int
			err = db.QueryRow("SELECT cid FROM typecho_contents WHERE cid = 3").Scan(&cid)
			useCid := 3
			if err == nil {
				err = db.QueryRow("SELECT MAX(cid) + 1 FROM typecho_contents").Scan(&useCid)
				if err != nil || useCid == 0 {
					useCid = 100
				}
			}

			query := `REPLACE INTO typecho_contents 
				(cid, title, slug, created, modified, text, ` + "`order`" + `, authorId, template, type, status, password, commentsNum, allowComment, allowPing, allowFeed, parent) 
				VALUES 
				(?, '请查看你本题的flag', 'moectf-flag-2026', 1782617828, 1782617828, 
				'恭喜你成功做出了开发与运维基础方向的签到复仇题！\n\n你的 Flag 为：\n` + flagString + `\n\n请复制上方 Flag 前往比赛平台提交。', 
				0, 1, NULL, 'post', 'publish', NULL, 0, 1, 1, 1, 0);`

			_, err = db.Exec(query, useCid)
			if err != nil {
				db.Close()
				continue
			}

			flagInjected = true
		}

		for {
			time.Sleep(15 * time.Second)
			db, err := sql.Open("mysql", dsn)
			if err == nil {
				if flagExists(db, flagString) {
					db.Close()
					continue
				}
				var cid int
				db.QueryRow("SELECT MAX(cid) + 1 FROM typecho_contents").Scan(&cid)
				if cid == 0 {
					cid = 100
				}
				query := `REPLACE INTO typecho_contents 
					(cid, title, slug, created, modified, text, ` + "`order`" + `, authorId, template, type, status, password, commentsNum, allowComment, allowPing, allowFeed, parent) 
					VALUES 
					(?, '请查看你本题的flag', 'moectf-flag-2026', 1782617828, 1782617828, 
					'恭喜你成功做出了开发与运维基础方向的签到复仇题！\n\n你的 Flag 为：\n` + flagString + `\n\n请复制上方 Flag 前往比赛平台提交。', 
					0, 1, NULL, 'post', 'publish', NULL, 0, 1, 1, 1, 0);`
				db.Exec(query, cid)
				db.Close()
			}
		}
	}
}
