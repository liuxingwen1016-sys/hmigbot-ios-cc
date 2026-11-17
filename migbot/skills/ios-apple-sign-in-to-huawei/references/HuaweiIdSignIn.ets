import { LoginWithHuaweiIDButton, loginComponentManager } from '@kit.AccountKit'
import { BusinessError } from '@kit.BasicServicesKit'

export interface HuaweiSignInCallbacks {
  onCode(code: string): void
  onError(code: number): void
  onMissingCode(): void
}

@ComponentV2
export struct HuaweiIdSignIn {
  @Require @Param callbacks: HuaweiSignInCallbacks
  @Param busy: boolean = false

  private controller: loginComponentManager.LoginWithHuaweiIDButtonController =
    new loginComponentManager.LoginWithHuaweiIDButtonController()
      .onClickLoginWithHuaweiIDButton((error: BusinessError, credential: loginComponentManager.HuaweiIDCredential) => {
        if (this.busy) {
          return
        }
        if (error) {
          this.callbacks.onError(error.code)
          return
        }
        if (!credential?.authorizationCode) {
          this.callbacks.onMissingCode()
          return
        }
        this.callbacks.onCode(credential.authorizationCode)
      })

  build() {
    LoginWithHuaweiIDButton({
      params: {
        style: loginComponentManager.Style.BUTTON_BLACK,
        loginType: loginComponentManager.LoginType.ID,
        supportDarkMode: true
      },
      controller: this.controller
    })
      .enabled(!this.busy)
  }
}
