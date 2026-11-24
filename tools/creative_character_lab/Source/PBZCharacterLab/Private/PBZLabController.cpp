#include "PBZLab.h"
#include "Engine/Engine.h"
#include "Engine/GameViewportClient.h"
#include "Engine/Canvas.h"
#include "InputKeyEventArgs.h"
#include "Components/InputComponent.h"
#include "GameFramework/CharacterMovementComponent.h"
#include "GameFramework/PlayerInput.h"
#include "Framework/Application/SlateApplication.h"
#include "Widgets/SCompoundWidget.h"
#include "Widgets/Layout/SBorder.h"
#include "Widgets/Layout/SBox.h"
#include "Widgets/Layout/SScrollBox.h"
#include "Widgets/SBoxPanel.h"
#include "Widgets/Input/SButton.h"
#include "Widgets/Text/STextBlock.h"

class SPBZRolePanel : public SCompoundWidget
{
public:
    SLATE_BEGIN_ARGS(SPBZRolePanel) {} SLATE_ARGUMENT(TWeakObjectPtr<APBZLabController>, Controller) SLATE_END_ARGS()
    TWeakObjectPtr<APBZLabController> Controller;
    void Construct(const FArguments& Args)
    {
        Controller = Args._Controller;
        TSharedRef<SVerticalBox> Rows = SNew(SVerticalBox);
        Rows->AddSlot().AutoHeight().Padding(10)[SNew(STextBlock).Text(FText::FromString(TEXT("选择角色")))];
        const auto* LabPawn = Controller.IsValid() ? Cast<APBZLabCharacter>(Controller->GetPawn()) : nullptr;
        if (LabPawn && LabPawn->Catalog)
        {
            for (int32 Index = 0; Index < LabPawn->Catalog->Roles.Num(); ++Index)
            {
                const auto& RoleSpec = LabPawn->Catalog->Roles[Index];
                Rows->AddSlot().AutoHeight().Padding(5)[SNew(SButton)
                    .Text(FText::Format(FText::FromString(TEXT("{0}  {1}")), FText::AsNumber(Index + 1), RoleSpec.Name))
                    .OnClicked_Lambda([Weak=Controller, Index]()
                    { if (Weak.IsValid()) Weak->ChooseRole(Index); return FReply::Handled(); })];
            }
        }
        Rows->AddSlot().AutoHeight().Padding(10)[SNew(STextBlock).Text(FText::FromString(TEXT("Tab / Esc 返回")))];
        ChildSlot.HAlign(HAlign_Center).VAlign(VAlign_Center)[SNew(SBox).WidthOverride(500).MaxDesiredHeight(620)
            [SNew(SBorder).Padding(16).BorderBackgroundColor(FLinearColor(.03f,.04f,.06f,.98f))
                [SNew(SScrollBox) + SScrollBox::Slot()[Rows]]]];
    }
    virtual bool SupportsKeyboardFocus() const override { return true; }
    virtual FReply OnKeyDown(const FGeometry&, const FKeyEvent& Event) override
    {
        if (Event.GetKey() == EKeys::Escape || Event.GetKey() == EKeys::Tab)
        { if (Controller.IsValid()) Controller->ToggleSelector(); return FReply::Handled(); }
        return FReply::Unhandled();
    }
};

void APBZLabController::SetupInputComponent()
{
    Super::SetupInputComponent();
    // The integrated profile defines degrees per mouse unit. Do not multiply
    // it again by the engine's default .07 mouse-axis sensitivity.
    if (PlayerInput) PlayerInput->SetMouseSensitivity(1.f);
    InputComponent->BindAxisKey(EKeys::MouseX, this, &APBZLabController::Yaw);
    InputComponent->BindAxisKey(EKeys::MouseY, this, &APBZLabController::Pitch);
    auto Bind = [this](FKey Key, TFunction<void()> Function)
    {
        FInputKeyBinding Binding(FInputChord(Key), IE_Pressed);
        Binding.KeyDelegate.GetDelegateForManualSet().BindLambda(MoveTemp(Function));
        InputComponent->KeyBindings.Add(MoveTemp(Binding));
    };
    Bind(EKeys::Tab, [this]() { ToggleSelector(); });
    const FKey Roles[] = { EKeys::One, EKeys::Two, EKeys::Three, EKeys::Four, EKeys::Five, EKeys::Six };
    for (int32 Index = 0; Index < 6; ++Index) Bind(Roles[Index], [this, Index]() { ChooseRole(Index); });
    const FKey Actions[] = { EKeys::LeftMouseButton, EKeys::Q, EKeys::E, EKeys::R, EKeys::F };
    for (int32 Slot = 0; Slot < 5; ++Slot) Bind(Actions[Slot], [this, Slot]()
    { if (!IsSelectorOpen()) if (auto* LabPawn = Cast<APBZLabCharacter>(GetPawn())) LabPawn->PlayAction(Slot); });
    Bind(EKeys::MiddleMouseButton, [this]()
    { if (!IsSelectorOpen()) if (auto* LabPawn = Cast<APBZLabCharacter>(GetPawn())) LabPawn->ToggleLock(); });
    Bind(EKeys::SpaceBar, [this]()
    { if (!IsSelectorOpen()) if (auto* LabPawn = Cast<APBZLabCharacter>(GetPawn())) LabPawn->Jump(); });
    FInputKeyBinding Release(FInputChord(EKeys::SpaceBar), IE_Released);
    Release.KeyDelegate.GetDelegateForManualSet().BindLambda([this]()
    { if (auto* LabPawn = Cast<APBZLabCharacter>(GetPawn())) LabPawn->StopJumping(); });
    InputComponent->KeyBindings.Add(MoveTemp(Release));
}

void APBZLabController::Yaw(float Value) { if (auto* C = Cast<APBZLabCharacter>(GetPawn())) C->Look(Value, 0); }
void APBZLabController::Pitch(float Value) { if (auto* C = Cast<APBZLabCharacter>(GetPawn())) C->Look(0, Value); }
void APBZLabController::CloseSelector()
{
    if (Selector.IsValid() && GetWorld() && GetWorld()->GetGameViewport())
        GetWorld()->GetGameViewport()->RemoveViewportWidgetContent(Selector.ToSharedRef());
    Selector.Reset();
    bShowMouseCursor = false;
    SetInputMode(FInputModeGameOnly());
}

void APBZLabController::ToggleSelector()
{
    if (Selector.IsValid()) { CloseSelector(); return; }
    if (!GetWorld() || !GetWorld()->GetGameViewport()) return;
    auto* LabPawn = Cast<APBZLabCharacter>(GetPawn());
    if (!LabPawn || !LabPawn->Catalog) return;
    LabPawn->GetCharacterMovement()->StopMovementImmediately();
    Selector = SNew(SPBZRolePanel).Controller(TWeakObjectPtr<APBZLabController>(this));
    GetWorld()->GetGameViewport()->AddViewportWidgetContent(Selector.ToSharedRef(), 30);
    bShowMouseCursor = true;
    SetInputMode(FInputModeGameAndUI().SetWidgetToFocus(Selector).SetHideCursorDuringCapture(false));
}

void APBZLabController::ChooseRole(int32 Index)
{
    if (auto* LabPawn = Cast<APBZLabCharacter>(GetPawn()))
        if (LabPawn->SelectRole(Index) && Selector.IsValid()) CloseSelector();
}

bool APBZLabController::InjectLabInput(FName Key, float Amount, bool Axis, bool Release)
{
    if (!GetWorld() || !GetWorld()->IsGameWorld()) return false;
    const FKey Input(Key);
    if (!Input.IsValid()) return false;
    return InputKey(FInputKeyEventArgs::CreateSimulated(Input,
        Axis ? IE_Axis : (Release ? IE_Released : IE_Pressed), Amount, Axis ? 1 : -1));
}

void APBZLabController::EndPlay(const EEndPlayReason::Type Reason)
{
    CloseSelector();
    Super::EndPlay(Reason);
}

void APBZLabHUD::DrawHUD()
{
    Super::DrawHUD();
    const auto* LabPawn = Cast<APBZLabCharacter>(GetOwningPawn());
    if (!Canvas || !LabPawn) return;
    DrawRect(FLinearColor(0,0,0,.65f), 12, 12, 720, 124);
    DrawText(LabPawn->Status.ToString(), FLinearColor::White, 26, 22, GEngine->GetMediumFont(), 1.1f);
    DrawText(TEXT("WASD 移动 | 鼠标 镜头 | 中键 锁定 | 空格 跳跃"), FLinearColor::White, 26, 50);
    DrawText(TEXT("Tab 角色选择 | 1-6 切换角色 | 左键 / Q / E / R / F 动作"), FLinearColor::White, 26, 70);
    if (LabPawn->Catalog && LabPawn->Catalog->Roles.IsValidIndex(LabPawn->RoleIndex))
    {
        FString Actions;
        const TCHAR* Keys[] = {TEXT("左键"),TEXT("Q"),TEXT("E"),TEXT("R"),TEXT("F")};
        const auto& RoleSpec = LabPawn->Catalog->Roles[LabPawn->RoleIndex];
        for (int32 I = 0; I < FMath::Min(5, RoleSpec.Actions.Num()); ++I)
            Actions += FString::Printf(TEXT("%s: %s   "), Keys[I], *RoleSpec.Actions[I].Name.ToString());
        DrawText(Actions, FLinearColor(.8f,.9f,1), 26, 96);
    }
}

APBZLabGameMode::APBZLabGameMode()
{
    DefaultPawnClass = APBZLabCharacter::StaticClass();
    PlayerControllerClass = APBZLabController::StaticClass();
    HUDClass = APBZLabHUD::StaticClass();
}
