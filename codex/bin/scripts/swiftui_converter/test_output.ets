@Entry
@Component
struct ContentView {
  @State
  count: number = 0
  @State
  message: string = "Hello"

  build() {
    Column({ space: 20 }) {
    Text(`Count: ${this.count}`)
    .fontSize(20)
    .fontWeight(FontWeight.Bold)
    .fontColor(Color.Blue)

    Text(this.message)

    Button("Increment")
    .onClick(() => {
    this.count += 1
    })
    .padding(10)
    .backgroundColor(Color.Green)
    }
  }
}