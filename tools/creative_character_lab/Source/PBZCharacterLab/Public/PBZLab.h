#pragma once
#include "CoreMinimal.h"
#include "Engine/DataAsset.h"
#include "Animation/AnimInstance.h"
#include "GameFramework/Character.h"
#include "GameFramework/PlayerController.h"
#include "GameFramework/HUD.h"
#include "GameFramework/GameModeBase.h"
#include "PBZLab.generated.h"

class UAnimSequence;
class USkeletalMesh;
class USpringArmComponent;
class UCameraComponent;
struct FStreamableHandle;
class SWidget;

USTRUCT(BlueprintType)
struct FPBZLabAction
{
    GENERATED_BODY()
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="角色调试") FText Name;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="角色调试") TSoftObjectPtr<UAnimSequence> Animation;
};

USTRUCT(BlueprintType)
struct FPBZLabRole
{
    GENERATED_BODY()
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="角色调试") FName Id;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="角色调试") FText Name;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="角色调试") TSoftObjectPtr<USkeletalMesh> Mesh;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="角色调试") TSoftObjectPtr<UAnimSequence> Idle;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="角色调试") TSoftObjectPtr<UAnimSequence> Walk;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="角色调试") bool MeshPreviewOnly = false;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="角色调试") TArray<FPBZLabAction> Actions;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="角色调试", meta=(ClampMin="150", ClampMax="900")) float Speed = 480;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="角色调试", meta=(ClampMin="90", ClampMax="900")) float TurnRate = 540;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="角色调试", meta=(ClampMin="0.05", ClampMax="1")) float MouseScale = .22f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="角色调试", meta=(ClampMin="0", ClampMax="0.25")) float BufferSeconds = .18f;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="角色调试", meta=(ClampMin="0.25", ClampMax="10")) float UnlockDegrees = 1;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="角色调试", meta=(ClampMin="10", ClampMax="45")) float LookStepDegrees = 45;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="角色调试") float MeshYaw = -90;
};

UCLASS(BlueprintType)
class PBZCHARACTERLAB_API UPBZLabCatalog : public UDataAsset
{
    GENERATED_BODY()
public:
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="角色调试") TArray<FPBZLabRole> Roles;
};

UCLASS(Transient)
class PBZCHARACTERLAB_API UPBZLabAnimInstance : public UAnimInstance
{
    GENERATED_BODY()
protected:
    virtual FAnimInstanceProxy* CreateAnimInstanceProxy() override;
    virtual void DestroyAnimInstanceProxy(FAnimInstanceProxy* Proxy) override;
};

UCLASS(Blueprintable)
class PBZCHARACTERLAB_API APBZLabCharacter : public ACharacter
{
    GENERATED_BODY()
public:
    APBZLabCharacter();
    virtual void BeginPlay() override;
    virtual void Tick(float DeltaSeconds) override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="角色库") TObjectPtr<UPBZLabCatalog> Catalog;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="角色调试") TObjectPtr<USpringArmComponent> CameraBoom;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="角色调试") TObjectPtr<UCameraComponent> Camera;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="角色调试") int32 RoleIndex = INDEX_NONE;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="角色调试") bool Loading = false;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="角色调试") int32 ActionSerial = 0;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="角色调试") float ActionElapsed = 0;
    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="角色调试") FText Status;
    UPROPERTY(Transient, VisibleAnywhere, BlueprintReadOnly, Category="角色调试") TObjectPtr<UAnimSequence> IdleClip;
    UPROPERTY(Transient, VisibleAnywhere, BlueprintReadOnly, Category="角色调试") TObjectPtr<UAnimSequence> WalkClip;
    UPROPERTY(Transient, VisibleAnywhere, BlueprintReadOnly, Category="角色调试") TObjectPtr<UAnimSequence> ActionClip;
    UPROPERTY(Transient, VisibleAnywhere, BlueprintReadOnly, Category="角色调试") TArray<TObjectPtr<UAnimSequence>> LoadedActions;
    UFUNCTION(BlueprintCallable, Category="角色调试") bool SelectRole(int32 Index);
    UFUNCTION(BlueprintCallable, Category="角色调试") bool PlayAction(int32 Slot);
    UFUNCTION(BlueprintCallable, Category="角色调试") void ToggleLock();
    UFUNCTION(BlueprintCallable, Category="角色调试") bool HasTarget() const { return Target.IsValid(); }
    UFUNCTION(BlueprintCallable, Category="角色调试") float GetActionRemaining() const;
    void Look(float Yaw, float Pitch);
private:
    TSharedPtr<FStreamableHandle> LoadHandle;
    uint64 LoadSerial = 0;
    TWeakObjectPtr<AActor> Target;
    FPBZLabRole Current;
    int32 PendingAction = INDEX_NONE;
    float BufferLeft = 0;
    float ManualLookAccumulated = 0;
    float ManualLookQuietTime = 0;
    void FinishLoad(int32 Index, uint64 Serial);
    bool StartAction(int32 Slot);
};

UCLASS()
class PBZCHARACTERLAB_API APBZLabController : public APlayerController
{
    GENERATED_BODY()
public:
    virtual void SetupInputComponent() override;
    virtual void EndPlay(const EEndPlayReason::Type Reason) override;
    UFUNCTION(BlueprintCallable, Category="角色调试") void ToggleSelector();
    UFUNCTION(BlueprintCallable, Category="角色调试") void ChooseRole(int32 Index);
    UFUNCTION(BlueprintCallable, Category="角色调试") bool IsSelectorOpen() const { return Selector.IsValid(); }
    UFUNCTION(BlueprintCallable, Category="角色调试|自动验收", meta=(DevelopmentOnly)) bool InjectLabInput(FName Key, float Amount, bool Axis, bool Release);
private:
    TSharedPtr<SWidget> Selector;
    void CloseSelector();
    void Yaw(float Value);
    void Pitch(float Value);
};

UCLASS()
class PBZCHARACTERLAB_API APBZLabHUD : public AHUD
{
    GENERATED_BODY()
public:
    virtual void DrawHUD() override;
};

UCLASS()
class PBZCHARACTERLAB_API APBZLabGameMode : public AGameModeBase
{
    GENERATED_BODY()
public:
    APBZLabGameMode();
};
