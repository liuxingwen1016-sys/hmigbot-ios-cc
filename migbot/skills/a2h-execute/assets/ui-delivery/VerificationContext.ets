// Generated verification helpers; no production provider, timer, or system clock mutation.
export class VerificationParameter {
  name: string;
  kind: string;
  textValue: string;
  numericValue: number;
  flagValue: boolean;

  constructor(name: string, kind: string, textValue: string, numericValue: number, flagValue: boolean) {
    this.name = name;
    this.kind = kind;
    this.textValue = textValue;
    this.numericValue = numericValue;
    this.flagValue = flagValue;
  }
}

export class DisplayClock {
  readonly enabled: boolean;
  readonly epochMs: number;
  readonly timeZone: string;
  readonly locale: string;

  constructor(enabled: boolean = false, epochMs: number = 0, timeZone: string = '', locale: string = '') {
    this.enabled = enabled;
    this.epochMs = epochMs;
    this.timeZone = timeZone;
    this.locale = locale;
  }

  // Inject only into date-label/formatting functions. Not a timer/deadline API.
  displayNow(): Date {
    return this.enabled ? new Date(this.epochMs) : new Date();
  }
}

export class ValidatedVerificationContext {
  readonly requestKey: string;
  readonly pageId: string;
  readonly stateId: string;
  readonly routeName: string;
  private parameters: VerificationParameter[];
  readonly visualFixture: boolean;
  readonly fixtureId: string;
  readonly displayClock: DisplayClock;

  constructor(requestKey: string, pageId: string, stateId: string, routeName: string,
    parameters: VerificationParameter[], visualFixture: boolean, fixtureId: string, displayClock: DisplayClock) {
    this.requestKey = requestKey;
    this.pageId = pageId;
    this.stateId = stateId;
    this.routeName = routeName;
    this.parameters = parameters;
    this.visualFixture = visualFixture;
    this.fixtureId = fixtureId;
    this.displayClock = displayClock;
  }

  private parameter(name: string, kind: string): VerificationParameter {
    for (const parameter of this.parameters) {
      if (parameter.name === name && parameter.kind === kind) {
        return parameter;
      }
    }
    throw new Error('Missing or wrong-type verification parameter: ' + name);
  }

  stringParam(name: string): string { return this.parameter(name, 'string').textValue; }
  numberParam(name: string): number { return this.parameter(name, 'number').numericValue; }
  booleanParam(name: string): boolean { return this.parameter(name, 'boolean').flagValue; }
}

// Pure decision helper, also exercised offline. A repeated Want does not grow the stack.
export function needsVerificationNavigation(lastKey: string, context: ValidatedVerificationContext,
  stackSize: number): boolean {
  return lastKey !== context.requestKey || stackSize === 0;
}
