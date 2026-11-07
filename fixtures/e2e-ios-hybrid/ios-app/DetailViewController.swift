import UIKit

final class DetailViewController: UIViewController {
    private let titleLabel = UILabel()
    private let actionButton = UIButton(type: .system)

    override func viewDidLoad() {
        super.viewDidLoad()
        titleLabel.text = NSLocalizedString("detail.title", comment: "")
        actionButton.setTitle("Done", for: .normal)
        let stack = UIStackView(arrangedSubviews: [titleLabel, actionButton])
        stack.axis = .vertical
        stack.spacing = 12
        view.addSubview(stack)
    }
}
