借鉴了 THEM?!CTF 2026 的 SANITY 4，想要做一个让大家一起参与的题目，最初的方案是这样：大家一起接龙，但只有一个人得到flag，这样并不好，而且还会鼓励高并发，要是有厉害的人捣乱大家都别玩了。

```go
package main

import (
	"log"
	"math"
	"net/http"
	"strconv"

	"github.com/gin-gonic/gin"
)

func main() {
	r := gin.Default()

	number := 1
	times := 0

	r.GET("/ping", func(c *gin.Context) {
		if number < int(math.Pow(2, float64(times))) {
			number++
			c.JSON(http.StatusOK, gin.H{
				"message": "number is not large enough, now it is " + strconv.Itoa(number),
			})
		} else {
			number = 0
			times++
			c.JSON(http.StatusOK, gin.H{
				"message": "the flag is moectf{aaabbbxxx}",
			})
		}
	})

	if err := r.Run(); err != nil {
		log.Fatalf("failed to run server: %v", err)
	}
}
```

所以改成题目中的那样，虽然变成单人游戏了，但选手群里有人做了一个公网版本，题目比较出圈。