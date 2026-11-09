@Component
struct SimpleView {
  build() {
    Column {
    Text(`Count: ${this.count}`)
    Button("Increment") {
    count += 1
    }
    }
  }
}