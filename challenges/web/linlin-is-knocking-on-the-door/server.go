package main

import (
	"log"
	"net/http"
	"os"
	"strconv"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/gorilla/websocket"
)

type MsgLog struct {
	Type    string `json:"type"`
	Time    string `json:"time"`
	User    string `json:"user"`
	Text    string `json:"text"`
	Current int    `json:"current"`
}

var (
	currentNumber = 0
	targetNumber  = 500
	chatHistory   = []MsgLog{}
	mu            sync.Mutex

	clients   = make(map[*websocket.Conn]bool)
	clientsMu sync.Mutex

	upgrader = websocket.Upgrader{
		CheckOrigin: func(r *http.Request) bool { return true },
	}
)

func main() {
	gin.SetMode(gin.ReleaseMode)
	r := gin.Default()

	r.LoadHTMLFiles("index.html")

	realFlag := os.Getenv("FLAG")
	if realFlag == "" {
		realFlag = "moectf{websocket_speedrun_and_network_control!}"
	}

	r.GET("/", func(c *gin.Context) {
		c.HTML(http.StatusOK, "index.html", nil)
	})

	r.GET("/ws", func(c *gin.Context) {
		ws, err := upgrader.Upgrade(c.Writer, c.Request, nil)
		if err != nil {
			log.Printf("Failed to upgrade ws: %v", err)
			return
		}

		clientsMu.Lock()
		clients[ws] = true
		clientsMu.Unlock()

		mu.Lock()
		for _, logMsg := range chatHistory {
			_ = ws.WriteJSON(logMsg)
		}
		_ = ws.WriteJSON(MsgLog{Type: "status", Current: currentNumber})
		mu.Unlock()

		go func() {
			defer func() {
				clientsMu.Lock()
				delete(clients, ws)
				clientsMu.Unlock()
				ws.Close()
			}()
			for {
				if _, _, err := ws.ReadMessage(); err != nil {
					break
				}
			}
		}()
	})

	r.POST("/chat", func(c *gin.Context) {
		var json struct {
			User string `json:"user"`
			Msg  int    `json:"msg"`
		}
		if err := c.ShouldBindJSON(&json); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"status": "error"})
			return
		}

		mu.Lock()
		timestamp := time.Now().Format("15:04:05")
		var broadcastMsg MsgLog

		if json.Msg == 0 {
			currentNumber = 0
			broadcastMsg = MsgLog{
				Type:    "chat",
				Time:    timestamp,
				User:    json.User,
				Text:    "📢 发送了 0！所有人报数进度被无情清空！",
				Current: 0,
			}
			appendLog(broadcastMsg)
			mu.Unlock()

			broadcastToAll(broadcastMsg)
			c.JSON(http.StatusOK, gin.H{"status": "reset"})
			return
		}

		if json.Msg == currentNumber+1 {
			currentNumber++
			if currentNumber == targetNumber {
				mu.Unlock()
				broadcastToAll(MsgLog{Type: "chat", Time: timestamp, User: "SYSTEM", Text: "🎉 终点达成！Flag 已经向全场公布！", Current: targetNumber})
				broadcastToAll(MsgLog{Type: "chat", Time: timestamp, User: "SYSTEM", Text: "祝贺玩家 [" + json.User + "]！Flag 为: " + realFlag, Current: targetNumber})
				c.JSON(http.StatusOK, gin.H{"status": "win"})
				return
			}

			broadcastMsg = MsgLog{
				Type:    "chat",
				Time:    timestamp,
				User:    json.User,
				Text:    "报数: " + strconv.Itoa(currentNumber),
				Current: currentNumber,
			}
			appendLog(broadcastMsg)
			mu.Unlock()

			broadcastToAll(broadcastMsg)
			c.JSON(http.StatusOK, gin.H{"status": "success"})
		} else {
			mu.Unlock()
			c.JSON(http.StatusOK, gin.H{"status": "fail"})
		}
	})

	if err := r.Run(":8080"); err != nil {
		log.Fatalf("Server failed: %v", err)
	}
}

func appendLog(msg MsgLog) {
	if len(chatHistory) > 50 {
		chatHistory = chatHistory[1:]
	}
	chatHistory = append(chatHistory, msg)
}

func broadcastToAll(msg MsgLog) {
	clientsMu.Lock()
	defer clientsMu.Unlock()
	for client := range clients {
		err := client.WriteJSON(msg)
		if err != nil {
			client.Close()
			delete(clients, client)
		}
	}
}
